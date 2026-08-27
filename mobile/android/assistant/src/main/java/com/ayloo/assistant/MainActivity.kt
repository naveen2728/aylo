package com.ayloo.assistant

import android.Manifest
import android.app.Activity
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Intent
import android.content.pm.PackageManager
import android.media.MediaRecorder
import android.os.Build
import android.os.Bundle
import android.os.SystemClock
import android.view.HapticFeedbackConstants
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

private val Ink = Color(0xFF071411)
private val Panel = Color(0xFF10231E)
private val SoftPanel = Color(0xFF173129)
private val Mint = Color(0xFF5BE6A8)
private val Pale = Color(0xFFE9FFF5)
private val Muted = Color(0xFF9DB8AC)

private enum class VoicePhase { IDLE, RECORDING, PROCESSING, SUCCESS, FAILURE }
private data class PendingVoice(val file: File, val durationMs: Long, val mode: VoiceMode)

class MainActivity : ComponentActivity() {
    private val api = AssistantApi()
    private var recorder: MediaRecorder? = null
    private var recordingFile: File? = null
    private var recordingStartedAt = 0L

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val processText = intent.takeIf { it.action == Intent.ACTION_PROCESS_TEXT }
            ?.getCharSequenceExtra(Intent.EXTRA_PROCESS_TEXT)?.toString()?.trim().orEmpty()
        val sharedText = intent.takeIf { it.action == Intent.ACTION_SEND }
            ?.getCharSequenceExtra(Intent.EXTRA_TEXT)?.toString()?.trim().orEmpty()
        val sourceText = processText.ifBlank { sharedText }
        val canReplace = intent.action == Intent.ACTION_PROCESS_TEXT &&
            !intent.getBooleanExtra(Intent.EXTRA_PROCESS_TEXT_READONLY, false)

        setContent {
            AylooTheme {
                if (sourceText.isNotBlank()) {
                    TextActionsScreen(
                        sourceText = sourceText,
                        canReplace = canReplace,
                        onAction = { action, onDone -> runTextAction(sourceText, action, canReplace, onDone) },
                        onClose = { finish() },
                    )
                } else {
                    VoiceScreen()
                }
            }
        }
    }

    override fun onDestroy() {
        recorder?.runCatching { stop() }
        recorder?.release()
        recorder = null
        recordingFile?.delete()
        recordingFile = null
        super.onDestroy()
    }

    private fun runTextAction(
        sourceText: String,
        action: TextAction,
        canReplace: Boolean,
        onDone: (Result<String>) -> Unit,
    ) {
        lifecycleScope.launch {
            val outcome = runCatching { withContext(Dispatchers.IO) { api.transform(sourceText, action) } }
            outcome.onSuccess { result ->
                copyText(result)
                if (canReplace) {
                    setResult(Activity.RESULT_OK, Intent().putExtra(Intent.EXTRA_PROCESS_TEXT, result))
                    finish()
                } else {
                    onDone(Result.success(result))
                }
            }.onFailure { onDone(Result.failure(it)) }
        }
    }

    private fun copyText(text: String) {
        getSystemService(ClipboardManager::class.java)
            .setPrimaryClip(ClipData.newPlainText("Ayloo result", text))
    }

    private fun startRecording(): Result<Unit> = runCatching {
        val pendingDir = File(filesDir, "pending_voice").apply { mkdirs() }
        val file = File(pendingDir, "command-${System.currentTimeMillis()}.m4a")
        @Suppress("DEPRECATION")
        val next = if (Build.VERSION.SDK_INT >= 31) MediaRecorder(this) else MediaRecorder()
        next.setAudioSource(MediaRecorder.AudioSource.MIC)
        next.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
        next.setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
        next.setAudioEncodingBitRate(128_000)
        next.setAudioSamplingRate(44_100)
        next.setOutputFile(file.absolutePath)
        next.prepare()
        next.start()
        recorder = next
        recordingFile = file
        recordingStartedAt = SystemClock.elapsedRealtime()
    }

    private fun stopRecording(mode: VoiceMode): Result<PendingVoice> = runCatching {
        val active = requireNotNull(recorder)
        val file = requireNotNull(recordingFile)
        val duration = SystemClock.elapsedRealtime() - recordingStartedAt
        active.stop()
        active.release()
        recorder = null
        recordingFile = null
        PendingVoice(file, duration, mode)
    }.onFailure {
        recorder?.runCatching { stop() }
        recorder?.release()
        recorder = null
        recordingFile?.delete()
        recordingFile = null
    }

    private fun savePending(pending: PendingVoice) {
        getSharedPreferences("pending", MODE_PRIVATE).edit()
            .putString("path", pending.file.absolutePath)
            .putLong("duration", pending.durationMs)
            .putString("mode", pending.mode.name)
            .apply()
    }

    private fun loadPending(): PendingVoice? {
        val prefs = getSharedPreferences("pending", MODE_PRIVATE)
        val path = prefs.getString("path", null) ?: return null
        val file = File(path)
        if (!file.exists()) {
            clearPending(null)
            return null
        }
        val mode = runCatching { VoiceMode.valueOf(prefs.getString("mode", "DICTATE")!!) }.getOrDefault(VoiceMode.DICTATE)
        return PendingVoice(file, prefs.getLong("duration", 1_000L), mode)
    }

    private fun clearPending(pending: PendingVoice?) {
        pending?.file?.delete()
        getSharedPreferences("pending", MODE_PRIVATE).edit().clear().apply()
    }

    @Composable
    private fun VoiceScreen() {
        val scope = rememberCoroutineScope()
        val view = LocalView.current
        var mode by remember { mutableStateOf(loadPending()?.mode ?: VoiceMode.DICTATE) }
        var pending by remember { mutableStateOf(loadPending()) }
        var phase by remember { mutableStateOf(if (pending == null) VoicePhase.IDLE else VoicePhase.FAILURE) }
        var message by remember {
            mutableStateOf(if (pending == null) "Tap the orb and speak" else "Your previous recording is ready to retry")
        }
        var resultPreview by remember { mutableStateOf("") }

        fun submit(item: PendingVoice) {
            savePending(item)
            pending = item
            phase = VoicePhase.PROCESSING
            message = "Working… the first request may take up to a minute"
            scope.launch {
                val outcome = runCatching {
                    withContext(Dispatchers.IO) { api.executeVoice(item.file, item.durationMs, item.mode) }
                }
                outcome.onSuccess { response ->
                    copyText(response.result)
                    clearPending(item)
                    pending = null
                    resultPreview = response.result
                    phase = VoicePhase.SUCCESS
                    message = "Copied — paste it anywhere"
                    view.performHapticFeedback(HapticFeedbackConstants.CONFIRM)
                }.onFailure {
                    phase = VoicePhase.FAILURE
                    message = it.message ?: "Ayloo could not connect. Your recording is safe."
                }
            }
        }

        fun finishRecording() {
            val outcome = stopRecording(mode)
            outcome.onSuccess { item ->
                if (item.durationMs < 250) {
                    item.file.delete()
                    phase = VoicePhase.FAILURE
                    message = "That was too short. Tap Retry and speak a little longer."
                } else {
                    submit(item)
                }
            }.onFailure {
                phase = VoicePhase.FAILURE
                message = "Recording stopped unexpectedly. Please retry."
            }
        }

        fun beginRecording() {
            clearPending(pending)
            pending = null
            resultPreview = ""
            startRecording().onSuccess {
                phase = VoicePhase.RECORDING
                message = "Listening… tap when you’re done"
                view.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
            }.onFailure {
                phase = VoicePhase.FAILURE
                message = "The microphone could not start. Check microphone access and retry."
            }
        }

        val permissionLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
            if (granted) beginRecording() else {
                phase = VoicePhase.FAILURE
                message = "Microphone access is needed only while you speak."
            }
        }

        LaunchedEffect(phase) {
            if (phase == VoicePhase.RECORDING) {
                delay(30_000)
                if (phase == VoicePhase.RECORDING) finishRecording()
            }
        }

        Column(
            modifier = Modifier.fillMaxSize().background(Ink).statusBarsPadding().navigationBarsPadding().padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(34.dp).clip(CircleShape).background(Mint), contentAlignment = Alignment.Center) {
                    Text("A", color = Ink, fontWeight = FontWeight.Black)
                }
                Spacer(Modifier.width(10.dp))
                Text("Ayloo", color = Pale, fontSize = 22.sp, fontWeight = FontWeight.Bold)
            }
            Spacer(Modifier.weight(1f))
            ModeSelector(mode = mode, enabled = phase != VoicePhase.RECORDING && phase != VoicePhase.PROCESSING) { mode = it }
            Spacer(Modifier.height(38.dp))
            VoiceOrb(phase) {
                when (phase) {
                    VoicePhase.RECORDING -> finishRecording()
                    VoicePhase.IDLE, VoicePhase.SUCCESS, VoicePhase.FAILURE -> {
                        if (ContextCompat.checkSelfPermission(this@MainActivity, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
                            beginRecording()
                        } else permissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
                    }
                    VoicePhase.PROCESSING -> Unit
                }
            }
            Spacer(Modifier.height(28.dp))
            AnimatedContent(targetState = message, label = "voice status") { status ->
                Text(status, color = if (phase == VoicePhase.FAILURE) Color(0xFFFFB7AE) else Pale, textAlign = TextAlign.Center, fontSize = 17.sp)
            }
            AnimatedVisibility(resultPreview.isNotBlank()) {
                Card(
                    colors = CardDefaults.cardColors(containerColor = Panel),
                    shape = RoundedCornerShape(20.dp),
                    modifier = Modifier.fillMaxWidth().padding(top = 24.dp),
                ) {
                    Text(resultPreview, color = Pale, maxLines = 5, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(18.dp))
                }
            }
            if (phase == VoicePhase.FAILURE) {
                Spacer(Modifier.height(22.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    pending?.let { item ->
                        Button(onClick = { submit(item) }, colors = ButtonDefaults.buttonColors(containerColor = Mint, contentColor = Ink)) {
                            Text("Retry")
                        }
                    }
                    OutlinedButton(onClick = {
                        clearPending(pending)
                        pending = null
                        phase = VoicePhase.IDLE
                        message = "Tap the orb and speak"
                    }) { Text(if (pending == null) "Reset" else "Discard", color = Pale) }
                }
            }
            Spacer(Modifier.weight(1f))
            Text("Private by design · no history", color = Muted, fontSize = 13.sp)
        }
    }
}

@Composable
private fun TextActionsScreen(
    sourceText: String,
    canReplace: Boolean,
    onAction: (TextAction, (Result<String>) -> Unit) -> Unit,
    onClose: () -> Unit,
) {
    var active by remember { mutableStateOf<TextAction?>(null) }
    var result by remember { mutableStateOf("") }
    var error by remember { mutableStateOf("") }
    val view = LocalView.current

    Column(
        modifier = Modifier.fillMaxSize().background(Ink).statusBarsPadding().navigationBarsPadding().padding(20.dp),
    ) {
        Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(34.dp).clip(CircleShape).background(Mint), contentAlignment = Alignment.Center) {
                Text("A", color = Ink, fontWeight = FontWeight.Black)
            }
            Spacer(Modifier.width(10.dp))
            Column(Modifier.weight(1f)) {
                Text("Transform with Ayloo", color = Pale, fontSize = 20.sp, fontWeight = FontWeight.Bold)
                Text(if (canReplace) "One tap replaces your selection" else "One tap copies the result", color = Muted, fontSize = 13.sp)
            }
            Text("Close", color = Muted, modifier = Modifier.clip(RoundedCornerShape(12.dp)).clickable(onClick = onClose).padding(10.dp))
        }
        Spacer(Modifier.height(22.dp))
        Card(colors = CardDefaults.cardColors(containerColor = Panel), shape = RoundedCornerShape(20.dp), modifier = Modifier.fillMaxWidth()) {
            Text(
                sourceText,
                color = Pale,
                maxLines = 5,
                overflow = TextOverflow.Ellipsis,
                lineHeight = 21.sp,
                modifier = Modifier.padding(18.dp),
            )
        }
        Spacer(Modifier.height(18.dp))
        Text("Choose one action", color = Muted, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(10.dp))
        LazyVerticalGrid(
            columns = GridCells.Fixed(2),
            verticalArrangement = Arrangement.spacedBy(10.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            userScrollEnabled = false,
            modifier = Modifier.height(254.dp),
        ) {
            items(TextAction.entries) { action ->
                val selected = active == action
                Surface(
                    color = if (selected) Mint.copy(alpha = .18f) else SoftPanel,
                    shape = RoundedCornerShape(18.dp),
                    modifier = Modifier.height(78.dp).clickable(enabled = active == null && result.isBlank()) {
                        view.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
                        active = action
                        error = ""
                        onAction(action) { outcome ->
                            outcome.onSuccess { result = it }.onFailure { error = it.message ?: "Please retry." }
                            active = null
                        }
                    },
                ) {
                    Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                        if (selected) {
                            CircularProgressIndicator(color = Mint, strokeWidth = 2.dp, modifier = Modifier.size(22.dp))
                            Spacer(Modifier.width(10.dp))
                        }
                        Column {
                            Text(action.title, color = Pale, fontWeight = FontWeight.SemiBold, fontSize = 15.sp)
                            Text(action.detail, color = Muted, fontSize = 12.sp, maxLines = 1)
                        }
                    }
                }
            }
        }
        AnimatedVisibility(error.isNotBlank()) {
            Text(error, color = Color(0xFFFFB7AE), modifier = Modifier.padding(top = 18.dp))
        }
        AnimatedVisibility(result.isNotBlank()) {
            Column(Modifier.padding(top = 18.dp)) {
                Text("Copied", color = Mint, fontWeight = FontWeight.Bold)
                Text(result, color = Pale, maxLines = 5, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(top = 8.dp))
                Button(
                    onClick = onClose,
                    colors = ButtonDefaults.buttonColors(containerColor = Mint, contentColor = Ink),
                    modifier = Modifier.fillMaxWidth().padding(top = 16.dp),
                ) { Text("Done") }
            }
        }
        Spacer(Modifier.weight(1f))
        Text("The result is also copied as a backup", color = Muted, fontSize = 12.sp, modifier = Modifier.align(Alignment.CenterHorizontally))
    }
}

@Composable
private fun ModeSelector(mode: VoiceMode, enabled: Boolean, onMode: (VoiceMode) -> Unit) {
    Surface(color = Panel, shape = RoundedCornerShape(24.dp)) {
        Row(Modifier.padding(4.dp)) {
            listOf(VoiceMode.DICTATE to "Dictate", VoiceMode.COMMAND to "Ask AI").forEach { (item, label) ->
                val selected = mode == item
                Surface(
                    color = if (selected) Mint else Color.Transparent,
                    contentColor = if (selected) Ink else Muted,
                    shape = RoundedCornerShape(20.dp),
                    modifier = Modifier.clickable(enabled = enabled) { onMode(item) },
                ) { Text(label, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(horizontal = 24.dp, vertical = 10.dp)) }
            }
        }
    }
}

@Composable
private fun VoiceOrb(phase: VoicePhase, onClick: () -> Unit) {
    val transition = rememberInfiniteTransition(label = "orb")
    val pulse by transition.animateFloat(
        initialValue = 1f,
        targetValue = if (phase == VoicePhase.RECORDING) 1.08f else 1f,
        animationSpec = infiniteRepeatable(tween(700), RepeatMode.Reverse),
        label = "pulse",
    )
    val scale by animateFloatAsState(if (phase == VoicePhase.PROCESSING) .94f else pulse, label = "orb scale")
    val color = when (phase) {
        VoicePhase.RECORDING -> Color(0xFFFF766C)
        VoicePhase.PROCESSING -> Color(0xFF69B9FF)
        VoicePhase.SUCCESS -> Mint
        else -> Color(0xFF55DFA3)
    }
    Box(
        modifier = Modifier.size(174.dp).scale(scale).clip(CircleShape)
            .background(Brush.radialGradient(listOf(color, color.copy(alpha = .48f), SoftPanel)))
            .clickable(
                enabled = phase != VoicePhase.PROCESSING,
                interactionSource = remember { MutableInteractionSource() },
                indication = null,
                onClick = onClick,
            ),
        contentAlignment = Alignment.Center,
    ) {
        if (phase == VoicePhase.PROCESSING) {
            CircularProgressIndicator(color = Pale, strokeWidth = 3.dp, modifier = Modifier.size(46.dp))
        } else {
            Text(if (phase == VoicePhase.RECORDING) "■" else "●", color = Pale, fontSize = 34.sp, modifier = Modifier.alpha(.95f))
        }
    }
}

@Composable
private fun AylooTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = darkColorScheme(primary = Mint, background = Ink, surface = Panel, onPrimary = Ink, onBackground = Pale),
        content = content,
    )
}
