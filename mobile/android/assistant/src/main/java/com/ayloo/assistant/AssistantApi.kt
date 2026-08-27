package com.ayloo.assistant

import okhttp3.FormBody
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

enum class TextAction(val wireName: String, val title: String, val detail: String) {
    IMPROVE("improve", "Improve", "Clearer, more natural"),
    GRAMMAR("grammar", "Fix grammar", "Correct mistakes"),
    SHORTEN("shorten", "Shorten", "Keep the key points"),
    SUMMARIZE("summarize", "Summarize", "Extract essentials"),
    PROFESSIONAL("professional", "Professional", "Polished tone"),
    REPLY("reply", "Write reply", "Respond naturally"),
}

data class VoiceResponse(val transcript: String, val result: String)

class AssistantApi(
    private val baseUrl: String = BuildConfig.API_BASE_URL,
    private val token: String = BuildConfig.TESTER_TOKEN,
) {
    private val client = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        // A sleeping Render Free service can need roughly a minute to wake.
        .readTimeout(150, TimeUnit.SECONDS)
        .callTimeout(150, TimeUnit.SECONDS)
        .build()

    fun transform(text: String, action: TextAction): String {
        val body = FormBody.Builder()
            .add("text", text)
            .add("action", action.wireName)
            .add("client_version", BuildConfig.VERSION_NAME)
            .build()
        return execute("/v1/text-actions", body).getString("result")
    }

    fun executeVoice(audio: File, durationMs: Long, mode: VoiceMode): VoiceResponse {
        val body = MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart("audio", audio.name, audio.asRequestBody("audio/mp4".toMediaType()))
            .addFormDataPart("client_version", BuildConfig.VERSION_NAME)
            .addFormDataPart("duration_ms", durationMs.toString())
            .addFormDataPart("mode", mode.name.lowercase())
            .build()
        val json = execute("/v1/commands", body)
        return VoiceResponse(json.getString("transcript"), json.getString("result"))
    }

    private fun execute(path: String, body: okhttp3.RequestBody): JSONObject {
        require(baseUrl.startsWith("https://") || baseUrl.startsWith("http://10.0.2.2")) {
            "Ayloo is not configured with a secure backend URL."
        }
        require(token.isNotBlank()) { "This internal build has no tester token." }
        val request = Request.Builder()
            .url(baseUrl.trimEnd('/') + path)
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
                return JSONObject(responseBody)
            }
        } catch (_: InterruptedIOException) {
            throw IOException("Ayloo may be waking up. Wait a moment, then tap Retry.")
        }
    }
}
