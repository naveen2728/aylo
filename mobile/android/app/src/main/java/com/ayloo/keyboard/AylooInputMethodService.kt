package com.ayloo.keyboard

import android.Manifest
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.content.res.ColorStateList
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.RippleDrawable
import android.inputmethodservice.InputMethodService
import android.media.MediaRecorder
import android.os.Handler
import android.os.Looper
import android.os.Build
import android.os.SystemClock
import android.view.Gravity
import android.view.HapticFeedbackConstants
import android.view.View
import android.view.inputmethod.InputMethodManager
import android.widget.Button
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.TextView
import java.io.File
import java.util.ArrayDeque
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
    // Session-only history: text never leaves the device and is cleared if Android stops the IME.
    private val aylooClipboard = ArrayDeque<String>()
    private var activeMode = VoiceMode.DICTATE
    private var recordingStartedAtMs = 0L
    private var stopRecording: Runnable? = null
    private var orbState = OrbState.IDLE
    private var status = "Ready · Dictate"
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
        root.setPadding(dp(5), dp(4), dp(5), dp(5))
        root.setBackgroundColor(KEYBOARD_BACKGROUND)

        root.addView(TextView(this).apply {
            text = status
            setTextColor(SECONDARY_TEXT)
            textSize = 11f
            gravity = Gravity.CENTER
            maxLines = 1
        }, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(22)))
        root.addView(row().also {
            it.gravity = Gravity.CENTER
            addCompactButton(it, "Dictate", 78, activeMode == VoiceMode.DICTATE) { selectDictate() }
            addCompactButton(it, "AI", 52, activeMode == VoiceMode.COMMAND) { selectCommand() }
            addCompactButton(it, orbLabel(), 42, true, orbState != OrbState.PROCESSING, orbColor()) { onOrbTapped() }
        }, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(38)))
        if (orbState == OrbState.RETRY) root.addView(row().also {
            addButton(it, "Retry", 1f, 42, false) { retryPending() }
            addButton(it, "Discard", 1f, 42, false) { discardPending() }
        })
        addClipboardStrip(root)
        if (symbols) addSymbolKeys(root) else addLetterKeys(root)
    }

    private fun addClipboardStrip(root: LinearLayout) {
        if (aylooClipboard.isEmpty()) return
        val clips = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        clips.addView(TextView(this).apply {
            text = "Ayloo clips"
            setTextColor(SECONDARY_TEXT)
            textSize = 12f
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(6), 0, dp(4), 0)
        }, LinearLayout.LayoutParams(dp(72), dp(38)))
        aylooClipboard.take(4).forEach { clip ->
            addClipboardButton(clips, clip) { currentInputConnection?.commitText(clip, 1) }
        }
        addClipboardButton(clips, "Clear") { aylooClipboard.clear(); refreshKeyboard() }
        root.addView(HorizontalScrollView(this).apply {
            isHorizontalScrollBarEnabled = false
            addView(clips)
        }, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(42)))
    }

    private fun addLetterKeys(root: LinearLayout) {
        addCharacterRow(root, if (uppercase) "QWERTYUIOP" else "qwertyuiop")
        root.addView(row().also { middle ->
            addSpacer(middle, .45f)
            (if (uppercase) "ASDFGHJKL" else "asdfghjkl").forEach { char -> addButton(middle, char.toString(), 1f, 48, false) { commitKey(char.toString()) } }
            addSpacer(middle, .45f)
        })
        root.addView(row().also { bottomLetters ->
            addButton(bottomLetters, if (uppercase) "⇧" else "⇧", 1.45f, 48, uppercase) { uppercase = !uppercase }
            (if (uppercase) "ZXCVBNM" else "zxcvbnm").forEach { char -> addButton(bottomLetters, char.toString(), 1f, 48, false) { commitKey(char.toString()) } }
            addButton(bottomLetters, "⌫", 1.45f, 48, false) { backspace() }
        })
        addBottomRow(root)
    }

    private fun addSymbolKeys(root: LinearLayout) {
        addCharacterRow(root, "1234567890")
        addCharacterRow(root, "@#₹_&-+()")
        root.addView(row().also { symbolsRow ->
            addButton(symbolsRow, "\\", 1.5f, 48, false) { commitKey("\\") }
            "*\"':;!?".forEach { char -> addButton(symbolsRow, char.toString(), 1f, 48, false) { commitKey(char.toString()) } }
            addButton(symbolsRow, "⌫", 1.5f, 48, false) { backspace() }
        })
        addBottomRow(root)
    }

    private fun addCharacterRow(root: LinearLayout, characters: String) {
        root.addView(row().also { keyRow ->
            characters.forEach { char -> addButton(keyRow, char.toString(), 1f, 48, false) { commitKey(char.toString()) } }
        })
    }

    private fun addBottomRow(root: LinearLayout) {
        root.addView(row().also {
            addButton(it, if (symbols) "ABC" else "123", 1.2f, 48, false) { symbols = !symbols }
            addButton(it, ",", .8f, 48, false) { commitKey(",") }
            addButton(it, "space", 3.2f, 48, false) { commitKey(" ") }
            addButton(it, ".", .8f, 48, false) { commitKey(".") }
            addButton(it, "⌨", 1.1f, 48, false) { switchKeyboard() }
            addButton(it, "↵", 1.2f, 48, false) { enter() }
        })
    }

    private fun row() = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
    private fun addSpacer(row: LinearLayout, weight: Float) {
        row.addView(View(this), LinearLayout.LayoutParams(0, dp(48), weight))
    }
    private fun selectDictate() = selectMode(VoiceMode.DICTATE)
    private fun selectCommand() = selectMode(VoiceMode.COMMAND)
    private fun orbLabel() = when (orbState) {
        OrbState.IDLE, OrbState.SUCCESS, OrbState.ERROR -> "✦"
        OrbState.RECORDING -> "●"
        OrbState.PROCESSING -> "···"
        OrbState.RETRY -> "↻"
    }
    private fun orbColor() = when (orbState) {
        OrbState.RECORDING -> RECORDING_COLOR
        OrbState.PROCESSING -> PROCESSING_COLOR
        OrbState.RETRY, OrbState.ERROR -> WARNING_COLOR
        else -> ACCENT_COLOR
    }
    private fun addButton(row: LinearLayout, label: String, weight: Float, height: Int, selected: Boolean, enabled: Boolean = true, onClick: () -> Unit) {
        row.addView(Button(this).apply {
            text = label
            textSize = 14f
            isAllCaps = false
            isEnabled = enabled
            minimumWidth = 0
            minimumHeight = 0
            minWidth = 0
            minHeight = 0
            setPadding(dp(2), 0, dp(2), 0)
            setTextColor(PRIMARY_TEXT)
            typeface = if (selected) Typeface.DEFAULT_BOLD else Typeface.DEFAULT
            background = rippleBackground(if (selected) ACCENT_COLOR else KEY_COLOR, dp(9).toFloat())
            setOnClickListener { performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP); onClick() }
        }, LinearLayout.LayoutParams(0, dp(height), weight).apply { setMargins(dp(2), dp(2), dp(2), dp(2)) })
    }
    private fun addCompactButton(row: LinearLayout, label: String, width: Int, selected: Boolean, enabled: Boolean = true, color: Int? = null, onClick: () -> Unit) {
        row.addView(Button(this).apply {
            text = label
            textSize = 12f
            isAllCaps = false
            isEnabled = enabled
            minimumWidth = 0
            minimumHeight = 0
            minWidth = 0
            minHeight = 0
            setPadding(dp(6), 0, dp(6), 0)
            setTextColor(PRIMARY_TEXT)
            typeface = if (selected) Typeface.DEFAULT_BOLD else Typeface.DEFAULT
            background = rippleBackground(color ?: if (selected) ACCENT_COLOR else SURFACE_COLOR, dp(17).toFloat())
            setOnClickListener { performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP); onClick() }
        }, LinearLayout.LayoutParams(dp(width), dp(34)).apply { setMargins(dp(3), dp(2), dp(3), dp(2)) })
    }
    private fun addClipboardButton(row: LinearLayout, value: String, onClick: () -> Unit) {
        val label = if (value.length > 18) value.take(18) + "…" else value
        row.addView(Button(this).apply {
            text = label
            textSize = 12f
            isAllCaps = false
            minimumWidth = 0
            minimumHeight = 0
            minWidth = 0
            minHeight = 0
            setPadding(dp(8), 0, dp(8), 0)
            setTextColor(PRIMARY_TEXT)
            background = rippleBackground(SURFACE_COLOR, dp(9).toFloat())
            setOnClickListener { performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP); onClick() }
        }, LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, dp(34)).apply { setMargins(dp(2), dp(2), dp(2), dp(2)) })
    }
    private fun rippleBackground(color: Int, radius: Float): RippleDrawable {
        val content = GradientDrawable().apply {
            cornerRadius = radius
            setColor(color)
            setStroke(dp(1), Color.argb(38, 255, 255, 255))
        }
        return RippleDrawable(ColorStateList.valueOf(Color.argb(70, 255, 255, 255)), content, null)
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
            status = if (mode == VoiceMode.DICTATE) "Ready · Dictate" else "Ready · AI Command"
            refreshKeyboard()
        }
    }

    private fun hasMicPermission() = checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED

    private fun requestMicPermission() {
        status = "Microphone permission needed"
        refreshKeyboard()
        startActivity(Intent(this, PermissionActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }

    private fun startRecording() {
        val target = pendingStore.createFile()
        try {
            recorder = MediaRecorder(this).apply {
                setAudioSource(MediaRecorder.AudioSource.VOICE_RECOGNITION)
                setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
                setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
                setAudioChannels(1)
                setAudioEncodingBitRate(96_000)
                setAudioSamplingRate(16_000)
                setOutputFile(target.absolutePath)
                prepare()
                start()
            }
            activeAudio = target
            recordingStartedAtMs = SystemClock.elapsedRealtime()
            orbState = OrbState.RECORDING
            status = if (activeMode == VoiceMode.DICTATE) "Listening · Dictate" else "Listening · AI Command"
            refreshKeyboard()
            stopRecording = Runnable { if (orbState == OrbState.RECORDING) finishRecordingAndSubmit() }.also {
                mainHandler.postDelayed(it, MAX_RECORDING_MS)
            }
        } catch (_: Exception) {
            pendingStore.discard(target)
            orbState = OrbState.ERROR
            status = "Microphone unavailable · tap to retry"
            refreshKeyboard()
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
            status = "Too short · tap to retry"
            refreshKeyboard()
            return
        }
        submit(audio, (SystemClock.elapsedRealtime() - recordingStartedAtMs).coerceIn(1L, MAX_RECORDING_MS), activeMode)
    }

    private fun submit(audio: File, durationMs: Long = MAX_RECORDING_MS, mode: VoiceMode = activeMode) {
        orbState = OrbState.PROCESSING
        status = if (mode == VoiceMode.DICTATE) "Transcribing…" else "Thinking…"
        refreshKeyboard()
        executor.execute {
            try {
                val response = CommandApi().execute(audio, durationMs, mode)
                mainHandler.post {
                    if (mode == VoiceMode.DICTATE) insertOnly(response.transcript) else copyAndInsert(response.result)
                    pendingStore.discard(audio)
                    activeAudio = null
                    orbState = OrbState.SUCCESS
                    status = if (mode == VoiceMode.DICTATE) "Inserted" else "Inserted · copied"
                    refreshKeyboard()
                }
            } catch (exception: Exception) {
                mainHandler.post {
                    activeAudio = audio
                    orbState = OrbState.RETRY
                    status = exception.message ?: "Could not connect. Your recording is ready to retry."
                    refreshKeyboard()
                }
            }
        }
    }

    private fun retryPending() { pendingStore.pending()?.let { submit(it, mode = activeMode) } ?: run { orbState = OrbState.IDLE; status = "No saved recording"; refreshKeyboard() } }
    private fun discardPending() {
        pendingStore.discard(pendingStore.pending())
        activeAudio = null
        orbState = OrbState.IDLE
        status = "Recording discarded"
        refreshKeyboard()
    }

    private fun copyAndInsert(text: String) {
        (getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager)
            .setPrimaryClip(ClipData.newPlainText("Ayloo command", text))
        saveToAylooClipboard(text)
        currentInputConnection?.commitText(text, 1)
    }

    private fun insertOnly(text: String) {
        saveToAylooClipboard(text)
        currentInputConnection?.commitText(text, 1)
    }

    private fun saveToAylooClipboard(text: String) {
        val normalized = text.trim()
        if (normalized.isEmpty()) return
        aylooClipboard.remove(normalized)
        aylooClipboard.addFirst(normalized)
        while (aylooClipboard.size > MAX_CLIPBOARD_ITEMS) aylooClipboard.removeLast()
    }

    private fun commitKey(key: String) {
        currentInputConnection?.commitText(key, 1)
        if (!symbols && uppercase) uppercase = false
    }
    /** One tap deletes exactly one character, with a fallback for editors that reject code-point deletion. */
    private fun backspace() {
        val connection = currentInputConnection ?: return
        connection.beginBatchEdit()
        try {
            if (!connection.deleteSurroundingTextInCodePoints(1, 0)) {
                connection.deleteSurroundingText(1, 0)
            }
        } finally {
            connection.endBatchEdit()
        }
    }
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
        val KEYBOARD_BACKGROUND: Int = Color.rgb(15, 16, 21)
        val SURFACE_COLOR: Int = Color.rgb(37, 39, 48)
        val KEY_COLOR: Int = Color.rgb(44, 46, 56)
        val ACCENT_COLOR: Int = Color.rgb(124, 108, 255)
        val RECORDING_COLOR: Int = Color.rgb(225, 75, 91)
        val PROCESSING_COLOR: Int = Color.rgb(83, 86, 101)
        val WARNING_COLOR: Int = Color.rgb(218, 145, 55)
        val PRIMARY_TEXT: Int = Color.rgb(246, 247, 251)
        val SECONDARY_TEXT: Int = Color.rgb(174, 178, 193)
        const val MAX_RECORDING_MS = 30_000L
        const val MIN_AUDIO_BYTES = 1_000L
        const val MAX_CLIPBOARD_ITEMS = 8
    }
}
