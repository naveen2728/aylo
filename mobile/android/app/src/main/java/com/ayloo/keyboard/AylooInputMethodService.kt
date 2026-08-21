package com.ayloo.keyboard

import android.Manifest
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.inputmethodservice.InputMethodService
import android.media.MediaRecorder
import android.os.Handler
import android.os.Looper
import android.os.Build
import android.os.SystemClock
import android.view.Gravity
import android.view.View
import android.view.inputmethod.InputMethodManager
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import java.io.File
import java.util.concurrent.Executors

enum class OrbState { IDLE, RECORDING, PROCESSING, SUCCESS, RETRY, ERROR }

/** Native views keep the IME independent of an Activity lifecycle. */
class AylooInputMethodService : InputMethodService() {
    private val mainHandler = Handler(Looper.getMainLooper())
    private val executor = Executors.newSingleThreadExecutor()
    private lateinit var pendingStore: PendingCommandStore
    private var recorder: MediaRecorder? = null
    private var activeAudio: File? = null
    private var keyboardRoot: LinearLayout? = null
    private var activeMode = VoiceMode.DICTATE
        set(value) { field = value; refreshKeyboard() }
    private var recordingStartedAtMs = 0L
    private var stopRecording: Runnable? = null
    private var orbState = OrbState.IDLE
        set(value) { field = value; refreshKeyboard() }
    private var status = "Choose Dictate or AI Command, then tap the orb."
        set(value) { field = value; refreshKeyboard() }
    private var symbols = false
        set(value) { field = value; refreshKeyboard() }
    private var uppercase = false
        set(value) { field = value; refreshKeyboard() }

    override fun onCreate() {
        super.onCreate()
        pendingStore = PendingCommandStore(this)
    }

    override fun onCreateInputView(): View = LinearLayout(this).also {
        keyboardRoot = it
        refreshKeyboard()
    }

    private fun refreshKeyboard() {
        if (Looper.myLooper() != Looper.getMainLooper()) {
            mainHandler.post(::refreshKeyboard)
            return
        }
        val root = keyboardRoot ?: return
        root.removeAllViews()
        root.orientation = LinearLayout.VERTICAL
        root.setPadding(dp(4), dp(4), dp(4), dp(4))
        root.setBackgroundColor(Color.rgb(22, 21, 29))

        root.addView(TextView(this).apply {
            text = status
            setTextColor(Color.WHITE)
            textSize = 12f
            gravity = Gravity.CENTER
        }, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(28)))
        root.addView(row().also {
            addButton(it, "Dictate", 1f, 38, activeMode == VoiceMode.DICTATE, ::selectDictate)
            addButton(it, "AI Command", 1f, 38, activeMode == VoiceMode.COMMAND, ::selectCommand)
        })
        if (orbState == OrbState.RETRY) root.addView(row().also {
            addButton(it, "Retry", 1f, 42, false, ::retryPending)
            addButton(it, "Discard", 1f, 42, false, ::discardPending)
        })
        val letters = if (uppercase) listOf("QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM") else listOf("qwertyuiop", "asdfghjkl", "zxcvbnm")
        val rows = if (symbols) listOf("1234567890", "-/:;()₹&@\"", "#+=!?.,") else letters
        rows.forEach { chars -> root.addView(row().also { keyboardRow ->
            chars.forEach { char -> addButton(keyboardRow, char.toString(), 1f, 48, false) { commitKey(char.toString()) } }
        }) }
        root.addView(row().also {
            addButton(it, if (symbols) "ABC" else "123", 1.1f, 48, false) { symbols = !symbols }
            addButton(it, "⇧", .9f, 48, false) { uppercase = !uppercase }
            addButton(it, "⌫", 1.1f, 48, false, ::backspace)
            addButton(it, orbLabel(), 1.4f, 48, true, ::onOrbTapped, orbState != OrbState.PROCESSING)
            addButton(it, "space", 3f, 48, false) { commitKey(" ") }
            addButton(it, "↵", 1.1f, 48, false, ::enter)
            addButton(it, "⌨", 1.1f, 48, false, ::switchKeyboard)
        })
    }

    private fun row() = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
    private fun selectDictate() = selectMode(VoiceMode.DICTATE)
    private fun selectCommand() = selectMode(VoiceMode.COMMAND)
    private fun orbLabel() = when (orbState) {
        OrbState.IDLE, OrbState.SUCCESS, OrbState.ERROR -> "● AI"
        OrbState.RECORDING -> "■ Stop"
        OrbState.PROCESSING -> "…"
        OrbState.RETRY -> "↻ Retry"
    }
    private fun addButton(row: LinearLayout, label: String, weight: Float, height: Int, selected: Boolean, onClick: () -> Unit, enabled: Boolean = true) {
        row.addView(Button(this).apply {
            text = label
            textSize = 14f
            isAllCaps = false
            isEnabled = enabled
            setTextColor(Color.WHITE)
            background = GradientDrawable().apply {
                cornerRadius = dp(8).toFloat()
                setColor(if (selected) Color.rgb(120, 104, 255) else Color.rgb(48, 46, 58))
            }
            setOnClickListener { onClick() }
        }, LinearLayout.LayoutParams(0, dp(height), weight).apply { setMargins(dp(2), dp(2), dp(2), dp(2)) })
    }
    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()

    private fun onOrbTapped() {
        when (orbState) {
            OrbState.IDLE, OrbState.SUCCESS, OrbState.ERROR -> if (hasMicPermission()) startRecording() else requestMicPermission()
            OrbState.RECORDING -> finishRecordingAndSubmit()
            OrbState.RETRY -> retryPending()
            OrbState.PROCESSING -> Unit
        }
    }

    private fun selectMode(mode: VoiceMode) {
        if (orbState == OrbState.IDLE || orbState == OrbState.SUCCESS || orbState == OrbState.ERROR) {
            activeMode = mode
            status = if (mode == VoiceMode.DICTATE) "Dictate selected. Tap the orb to speak." else "AI Command selected. Tap the orb to speak."
        }
    }

    private fun hasMicPermission() = checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED

    private fun requestMicPermission() {
        status = "Allow microphone access, then tap the orb again."
        startActivity(Intent(this, PermissionActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }

    private fun startRecording() {
        val target = pendingStore.createFile()
        try {
            recorder = MediaRecorder(this).apply {
                setAudioSource(MediaRecorder.AudioSource.VOICE_RECOGNITION)
                setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
                setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
                setAudioEncodingBitRate(64_000)
                setAudioSamplingRate(16_000)
                setOutputFile(target.absolutePath)
                prepare()
                start()
            }
            activeAudio = target
            recordingStartedAtMs = SystemClock.elapsedRealtime()
            orbState = OrbState.RECORDING
            status = if (activeMode == VoiceMode.DICTATE) "Dictating… tap the orb when you are done." else "Listening for an AI command… tap the orb when you are done."
            stopRecording = Runnable { if (orbState == OrbState.RECORDING) finishRecordingAndSubmit() }.also {
                mainHandler.postDelayed(it, MAX_RECORDING_MS)
            }
        } catch (_: Exception) {
            pendingStore.discard(target)
            orbState = OrbState.ERROR
            status = "Microphone could not start. Check permission and try again."
        }
    }

    private fun finishRecordingAndSubmit() {
        stopRecording?.let(mainHandler::removeCallbacks)
        stopRecording = null
        val audio = activeAudio
        try { recorder?.stop() } catch (_: RuntimeException) { pendingStore.discard(audio) }
        recorder?.release()
        recorder = null
        if (audio == null || !audio.exists() || audio.length() < MIN_AUDIO_BYTES) {
            pendingStore.discard(audio)
            orbState = OrbState.ERROR
            status = "That recording was too short. Please try again."
            return
        }
        submit(audio, (SystemClock.elapsedRealtime() - recordingStartedAtMs).coerceIn(1L, MAX_RECORDING_MS), activeMode)
    }

    private fun submit(audio: File, durationMs: Long = MAX_RECORDING_MS, mode: VoiceMode = activeMode) {
        orbState = OrbState.PROCESSING
        status = if (mode == VoiceMode.DICTATE) "Transcribing…" else "Turning your command into text…"
        executor.execute {
            try {
                val response = CommandApi().execute(audio, durationMs, mode)
                mainHandler.post {
                    if (mode == VoiceMode.DICTATE) insertOnly(response.transcript) else copyAndInsert(response.result)
                    pendingStore.discard(audio)
                    activeAudio = null
                    orbState = OrbState.SUCCESS
                    status = if (mode == VoiceMode.DICTATE) "Transcript inserted." else "Answer inserted and copied."
                }
            } catch (exception: Exception) {
                mainHandler.post {
                    activeAudio = audio
                    orbState = OrbState.RETRY
                    status = exception.message ?: "Could not connect. Your recording is ready to retry."
                }
            }
        }
    }

    private fun retryPending() { pendingStore.pending()?.let { submit(it, mode = activeMode) } ?: run { orbState = OrbState.IDLE; status = "No pending recording." } }
    private fun discardPending() {
        pendingStore.discard(pendingStore.pending())
        activeAudio = null
        orbState = OrbState.IDLE
        status = "Recording discarded."
    }

    private fun copyAndInsert(text: String) {
        (getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager)
            .setPrimaryClip(ClipData.newPlainText("Ayloo command", text))
        currentInputConnection?.commitText(text, 1)
    }

    private fun insertOnly(text: String) { currentInputConnection?.commitText(text, 1) }

    private fun commitKey(key: String) {
        currentInputConnection?.commitText(key, 1)
        if (!symbols && uppercase) uppercase = false
    }
    private fun backspace() { currentInputConnection?.deleteSurroundingText(1, 0) }
    private fun enter() { currentInputConnection?.commitText("\n", 1) }

    private fun switchKeyboard() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            switchToNextInputMethod(false)
        } else {
            (getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager).showInputMethodPicker()
        }
    }

    override fun onDestroy() {
        stopRecording?.let(mainHandler::removeCallbacks)
        recorder?.release()
        executor.shutdownNow()
        super.onDestroy()
    }

    private companion object {
        const val MAX_RECORDING_MS = 30_000L
        const val MIN_AUDIO_BYTES = 1_000L
    }
}
