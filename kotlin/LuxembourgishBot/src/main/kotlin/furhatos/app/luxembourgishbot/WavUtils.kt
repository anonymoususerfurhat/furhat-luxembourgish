package furhatos.app.luxembourgishbot

import java.io.File
import java.io.FileOutputStream

fun buildWavFromPCM(pcm: ByteArray, sampleRate: Int = 16000): File {
    val file = File(System.getProperty("java.io.tmpdir"), "luxasr_${System.currentTimeMillis()}.wav")
    FileOutputStream(file).use { out ->
        val dataSize = pcm.size
        // RIFF header
        out.write("RIFF".toByteArray())
        out.write(intToLittleEndian(36 + dataSize))
        out.write("WAVE".toByteArray())
        // fmt chunk
        out.write("fmt ".toByteArray())
        out.write(intToLittleEndian(16))           // chunk size
        out.write(shortToLittleEndian(1))          // PCM format
        out.write(shortToLittleEndian(1))          // mono
        out.write(intToLittleEndian(sampleRate))   // sample rate
        out.write(intToLittleEndian(sampleRate * 2)) // byte rate
        out.write(shortToLittleEndian(2))          // block align
        out.write(shortToLittleEndian(16))         // bits per sample
        // data chunk
        out.write("data".toByteArray())
        out.write(intToLittleEndian(dataSize))
        out.write(pcm)
    }
    return file
}

private fun intToLittleEndian(value: Int): ByteArray = byteArrayOf(
    (value and 0xFF).toByte(),
    (value shr 8 and 0xFF).toByte(),
    (value shr 16 and 0xFF).toByte(),
    (value shr 24 and 0xFF).toByte()
)

private fun shortToLittleEndian(value: Int): ByteArray = byteArrayOf(
    (value and 0xFF).toByte(),
    (value shr 8 and 0xFF).toByte()
)