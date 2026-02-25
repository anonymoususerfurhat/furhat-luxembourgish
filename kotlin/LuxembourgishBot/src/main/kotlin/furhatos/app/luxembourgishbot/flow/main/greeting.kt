package furhatos.app.luxembourgishbot.flow.main

import furhatos.app.luxembourgishbot.OpenAIClient
import furhatos.app.luxembourgishbot.TTSClient
import furhatos.app.luxembourgishbot.flow.Parent
import furhatos.flow.kotlin.Audio
import furhatos.flow.kotlin.State
import furhatos.flow.kotlin.furhat
import furhatos.flow.kotlin.onResponse
import furhatos.flow.kotlin.state
import furhatos.flow.kotlin.users
import furhatos.gestures.Gestures
import furhatos.nlu.common.No
import furhatos.nlu.common.Yes
import java.awt.Color

val Greeting : State = state(Interaction) {

    onEntry {
        furhat.attend(users.current)
        furhat.ledStrip.solid(Color.GREEN)

//
//        // Generate joke via GPT
//        val (raw, jokeText, emotion) = call { OpenAIClient.generateGreeting() }
//                as Triple<String, String, String>
//
//        // Apply gesture based on emotion
//        when (emotion) {
//            "Laughing" -> furhat.gesture(Gestures.BigSmile)
//            "Happy"    -> furhat.gesture(Gestures.Smile)
//            else       -> furhat.gesture(Gestures.Smile)
//        }
//
//        // Synthesize and say the joke
//        val audioUrl = TTSClient.getUrl(jokeText, "lb", "")
//        furhat.say("Moien!!")

        // Laugh after the punchline
        furhat.gesture(Gestures.BigSmile)
        delay(500)

        // Transition to interaction
        goto(Interaction)
    }
}

