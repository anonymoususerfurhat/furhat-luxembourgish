package furhatos.app.luxembourgishbot

import furhatos.flow.kotlin.furhat.audiofeed.AudioFeedListener

object MicListener : AudioFeedListener {
    private val frames = mutableListOf<ByteArray>()
    var capturing = false

    override fun audioData(data: ByteArray) {
        if (!capturing) return
        // Stereo interleaved: L L R R L L R R
        // Extract left channel (microphone) only
        val mono = ByteArray(data.size / 2)
        var monoIdx = 0
        var i = 0
        while (i < data.size - 3) {
            mono[monoIdx++] = data[i]
            mono[monoIdx++] = data[i + 1]
            i += 4
        }
        frames.add(mono)
    }

    fun startCapture() {
        frames.clear()
        capturing = true
    }

    fun stopCapture(): ByteArray {
        capturing = false
        if (frames.isEmpty()) return ByteArray(0)
        return frames.fold(ByteArray(0)) { acc, bytes -> acc + bytes }
    }
}