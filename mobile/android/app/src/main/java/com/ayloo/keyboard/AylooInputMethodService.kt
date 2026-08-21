package com.ayloo.keyboard

import android.Manifest
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.inputmethodservice.InputMethodService
import android.media.MediaRecorder
import android.os.Handler
import android.os.Looper
import android.os.Build
import android.view.View
import android.view.inputmethod.InputMethodManager
import android.os.SystemClock
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.ComposeView
import androidx.compose.ui.platform.ViewCompositionStrategy
import java.io.File
import java.util.concurrent.Executors

enum class OrbState { IDLE, RECORDING, PROCESSING, SUCCESS, RETRY, ERROR }

class AylooInputMethodService : InputMethodService() {
    private val mainHandler = Handler(Looper.getMainLooper())
    private val executor = Executors.newSingleThreadExecutor()
    private lateinit var pendingStore: PendingCommandStore
    private var recorder: MediaRecorder? = null
    private var activeAudio: File? = null
    private var activeMode = VoiceMode.DICTATE
    private var recordingStartedAtMs = 0L
    private var stopRecording: Runnable? = null
    private var orbState by mutableStateOf(OrbState.IDLE)
    private var status by mutableStateOf("Choose Dictate or AI Command, then tap the orb.")
    private var symbols by mutableStateOf(false)
    private var uppercase by mutableStateOf(false)

    override fun onCreate() {
        super.onCreate()
        pendingStore = PendingCommandStore(this)
    }

    override fun onCreateInputView(): View = ComposeView(this).apply {
        setViewCompositionStrategy(ViewCompositionStrategy.DisposeOnDetachedFromWindow)
        setContent {
            KeyboardScreen(
                orbState = orbState,
                status = status,
                symbols = symbols,
                uppercase = uppercase,
                voiceMode = activeMode,
                onOrb = ::onOrbTapped,
                onRetry = ::retryPending,
                onDiscard = ::discardPending,
                onModeSelected = ::selectMode,
                onKey = ::commitKey,
                onBackspace = ::backspace,
                onSymbols = { symbols = !symbols },
                onCaps = { uppercase = !uppercase },
                onSpace = { commitKey(" ") },
                onEnter = ::enter,
                onSwitchKeyboard = ::switchKeyboard,
            )
        }
    }

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
