package furhatos.app.luxembourgishbot

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.TimeUnit

object TTSClient {
    private val client = OkHttpClient.Builder()
        .callTimeout(10, TimeUnit.SECONDS)
        .build()

    fun getUrl(text: String, lang: String, transcript: String,  lengthScale: Double = Config.TTS_LENGTH_SCALE): String {
        val payload = JSONObject()
            .put("text", text)
            .put("lang", lang)
            .put("transcript", transcript)
            .put("length_scale", lengthScale)

        val request = Request.Builder()
            .url(Config.TTS_SERVER)
            .post(payload.toString().toRequestBody("application/json".toMediaType()))
            .build()

        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                println("[TTS] Error: ${response.code}")
                return ""
            }
            val json = JSONObject(response.body?.string() ?: return "")
            return json.getString("url")
        }
    }
}