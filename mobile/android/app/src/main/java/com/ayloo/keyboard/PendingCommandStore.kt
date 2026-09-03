package com.ayloo.keyboard

import android.content.Context
import java.io.File

data class PendingCommand(val audio: File, val durationMs: Long, val mode: VoiceMode)

/** Audio remains in private app storage only until a successful request or explicit discard. */
class PendingCommandStore(context: Context) {
    private val directory = File(context.filesDir, "pending-commands").apply { mkdirs() }
    private val preferences = context.getSharedPreferences("ayloo_pending_command", Context.MODE_PRIVATE)

    fun createFile(): File = File(directory, "command-${System.currentTimeMillis()}.m4a")

    fun retain(audio: File, durationMs: Long, mode: VoiceMode) {
        preferences.edit()
            .putString(KEY_FILE_NAME, audio.name)
            .putLong(KEY_DURATION_MS, durationMs)
            .putString(KEY_MODE, mode.name)
            .apply()
    }

    fun pending(): PendingCommand? {
        val fileName = preferences.getString(KEY_FILE_NAME, null) ?: return null
        val audio = File(directory, fileName)
        if (!audio.exists() || !audio.isFile) {
            clearMetadata()
            return null
        }
        val mode = runCatching {
            VoiceMode.valueOf(preferences.getString(KEY_MODE, VoiceMode.DICTATE.name)!!)
        }.getOrDefault(VoiceMode.DICTATE)
        return PendingCommand(
            audio = audio,
            durationMs = preferences.getLong(KEY_DURATION_MS, 30_000L).coerceIn(1L, 30_000L),
            mode = mode,
        )
    }

    fun discard(file: File?) {
        file?.delete()
        if (file == null || preferences.getString(KEY_FILE_NAME, null) == file.name) clearMetadata()
    }

    private fun clearMetadata() {
        preferences.edit().clear().apply()
    }

    private companion object {
        const val KEY_FILE_NAME = "file_name"
        const val KEY_DURATION_MS = "duration_ms"
        const val KEY_MODE = "mode"
    }
}
