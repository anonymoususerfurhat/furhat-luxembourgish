package furhatos.app.luxembourgishbot.flow.main

import furhatos.app.luxembourgishbot.*
import furhatos.app.luxembourgishbot.flow.*
import furhatos.flow.kotlin.*
import furhatos.gestures.Gestures
import java.awt.Color

val dialogue = DialogueManager()

fun parseReply(raw: String): Triple<String, String, String> {
    val respEmotion = Regex("<response_emotion=(\\w+)>", RegexOption.IGNORE_CASE)
        .find(raw)?.groupValues?.get(1) ?: "Calm"
    val clean = raw.replace(Regex("<.*?>"), "").trim()
    // Strip any language prefix regardless of what GPT puts
    val text = clean.replace(Regex("^(lb|en|fr|de):\\s*"), "").trim()
    return Triple("lb", text, respEmotion)  // always lb
}

val Interaction = state(Parent) {

    onEntry {
        try {
            // This automatically enables the feed and registers the listener
            InteractionLogger.startSession(asrMode = "luxasr", llmBackend = "openai")
            furhat.audioFeed.addListener(MicListener)
            println("[AudioFeed] Listener registered - Research robot confirmed")
        } catch (e: Exception) {
            println("[AudioFeed] ERROR - may not be a Research robot: ${e.message}")
        }
        MicListener.startCapture()
        furhat.ledStrip.solid(Color.GREEN)
        furhat.listen()
    }

    onResponse {
        furhat.ledStrip.solid(Color.BLUE)
        val pcm = MicListener.stopCapture()

        var userText = ""

        if (pcm.isNotEmpty()) {
            println("[Audio] Captured ${pcm.size} bytes, sending to LuxASR...")
            val wavFile = buildWavFromPCM(pcm)
            userText = call { LuxASR.transcribe(wavFile) } as String
            wavFile.delete()
            println("[LuxASR] Transcript: $userText")
        }

        // Fallback to Furhat ASR if LuxASR returns empty
        if (userText.isBlank()) {
            userText = it.text
            println("[Fallback to Furhat ASR]: $userText")
        }

        if (userText.isBlank()) {
            MicListener.startCapture()
            furhat.listen()
            return@onResponse
        }

        dialogue.add("user", userText)
        furhat.gesture(Gestures.Thoughtful)

        val raw = call { OpenAIClient.chat(dialogue.getHistory()) } as String
        val (lang, spokenText, emotion) = parseReply(raw)

        dialogue.add("assistant", spokenText)

        val userEmotion = Regex("<user_emotion=(\\w+)>", RegexOption.IGNORE_CASE)
            .find(raw)?.groupValues?.get(1) ?: "Calm"

        InteractionLogger.logTurn(
            userText = userText,
            userEmotion = userEmotion,
            assistantText = spokenText,
            assistantEmotion = emotion
        )

        when (emotion) {
            "Happy" -> furhat.gesture(Gestures.Smile)
            "Sad"   -> furhat.gesture(Gestures.ExpressSad)
            "Angry" -> furhat.gesture(Gestures.ExpressAnger)
            else    -> furhat.gesture(Gestures.Thoughtful)
        }
        furhat.ledStrip.solid(Color.RED)
        val audioUrl = TTSClient.getUrl(spokenText, lang, userText)
        furhat.say { +Audio(audioUrl, spokenText) }

        MicListener.startCapture()
        furhat.ledStrip.solid(Color.GREEN)
        furhat.listen()
    }

    onNoResponse {
        MicListener.startCapture()
        furhat.ledStrip.solid(Color.GREEN)
        furhat.listen()
    }

    onUserLeave {
        InteractionLogger.endSession(completed = true, notes = "User left")
        MicListener.capturing = false
        dialogue.clear()
        goto(Idle)
    }
}