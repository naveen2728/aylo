package com.ayloo.keyboard

import android.content.Context
import java.io.File

/** Audio remains in private app storage only until a successful request or explicit discard. */
class PendingCommandStore(context: Context) {
    private val directory = File(context.filesDir, "pending-commands").apply { mkdirs() }

    fun createFile(): File = File(directory, "command-${System.currentTimeMillis()}.m4a")
    fun pending(): File? = directory.listFiles()?.filter { it.isFile }?.maxByOrNull { it.lastModified() }
    fun discard(file: File?) { file?.delete() }
}
