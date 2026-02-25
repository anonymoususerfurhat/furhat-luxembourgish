package furhatos.app.luxembourgishbot

import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.asRequestBody
import java.io.File
import java.security.SecureRandom
import java.security.cert.X509Certificate
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManager
import javax.net.ssl.X509TrustManager

object LuxASR {

    private val client: OkHttpClient by lazy {
        // Trust all certificates - needed because Furhat's JVM doesn't trust LuxASR's cert
        val trustAllCerts = arrayOf<TrustManager>(object : X509TrustManager {
            override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) {}
            override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {}
            override fun getAcceptedIssuers(): Array<X509Certificate> = arrayOf()
        })

        val sslContext = SSLContext.getInstance("SSL")
        sslContext.init(null, trustAllCerts, SecureRandom())

        OkHttpClient.Builder()
            .sslSocketFactory(sslContext.socketFactory, trustAllCerts[0] as X509TrustManager)
            .hostnameVerifier { _, _ -> true }
            .build()
    }

    fun transcribe(wav: File): String {
        val body = MultipartBody.Builder()
            .setType(MultipartBody.FORM)
            .addFormDataPart(
                "audio_file", wav.name,
                wav.asRequestBody("audio/wav".toMediaType())
            ).build()

        val request = Request.Builder()
            .url("${Config.LUXASR_URL}?diarization=Enabled&outfmt=text")
            .post(body)
            .build()

        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                println("[LuxASR] Error: ${response.code}")
                return ""
            }
            val text = response.body?.string() ?: return ""
            return text.replace(
                Regex("\\[.*?\\]\\s*SPEAKER_\\d+:\\s*", setOf(RegexOption.DOT_MATCHES_ALL)), ""
            ).trim()
        }
    }
}