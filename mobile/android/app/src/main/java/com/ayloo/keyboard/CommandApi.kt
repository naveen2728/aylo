package com.ayloo.keyboard

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.asRequestBody
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.io.InterruptedIOException
import java.util.concurrent.TimeUnit

enum class VoiceMode { DICTATE, COMMAND }

data class CommandResponse(val transcript: String, val result: String)

class CommandApi(
    private val baseUrl: String = BuildConfig.API_BASE_URL,
    private val token: String = BuildConfig.TESTER_TOKEN,
    private val client: OkHttpClient = OkHttpClient.Builder()
        // Render's Free service can take about a minute to wake after idle time.
        .connectTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .readTimeout(150, TimeUnit.SECONDS)
        .callTimeout(150, TimeUnit.SECONDS)
        .build(),
) {
    fun execute(audio: File, durationMs: Long, mode: VoiceMode): CommandResponse {
        require(baseUrl.startsWith("https://") || baseUrl.startsWith("http://10.0.2.2")) {
            "Ayloo is not configured with a secure backend URL."
        }
        require(token.isNotBlank()) { "This internal build has no tester token." }
        val body = MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart("audio", audio.name, audio.asRequestBody("audio/mp4".toMediaType()))
            .addFormDataPart("client_version", BuildConfig.VERSION_NAME)
            .addFormDataPart("duration_ms", durationMs.toString())
            .addFormDataPart("mode", mode.name.lowercase())
            .build()
        val request = Request.Builder().url(baseUrl.trimEnd('/') + "/v1/commands")
            .header("Authorization", "Bearer $token")
            .post(body)
            .build()
        try {
            client.newCall(request).execute().use { response ->
                val responseBody = response.body?.string().orEmpty()
                if (!response.isSuccessful) {
                    val detail = runCatching { JSONObject(responseBody).optString("detail") }.getOrDefault("")
                    throw IOException(detail.ifBlank { "Ayloo could not process this request (${response.code})." })
                }
                val json = JSONObject(responseBody)
                return CommandResponse(json.getString("transcript"), json.getString("result"))
            }
        } catch (_: InterruptedIOException) {
            throw IOException("Ayloo may be waking up. Wait a minute, then tap Retry.")
        }
    }
}
