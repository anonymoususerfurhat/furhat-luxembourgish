package furhatos.app.luxembourgishbot

import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.TimeUnit

object OpenAIClient {
    private val client = OkHttpClient.Builder()
        .callTimeout(15, TimeUnit.SECONDS)
        .build()

    val SYSTEM_PROMPT  = """
    You are Furhat, a friendly, attentive, human-like conversational partner engaging in face-to-face spoken interaction.
    Keep the greeting short. For example, if the user says Moien, you reply with MOien, Wie geet et?
    Donot ask very long questions like. Just be natural and wait for the user to initiate a context or conversation.
    Your task has three steps:
    1) Infer the emotional tone of the USER’s last utterance.
    2) Decide the appropriate emotional tone for YOUR response, as a human would.
    3) Respond naturally using that response emotion.

    HUMAN EMOTION ALIGNMENT RULES:  
    - If the user sounds Happy, respond in a similarly Happy and upbeat way.
    - If the user sounds Calm or Neutral, respond calmly and naturally.
    - If the user sounds Sad, respond with empathy and a calm, supportive tone.
    - If the user sounds Angry or frustrated, respond calmly and de-escalate. Acknowledge feelings, avoid confrontation, and be apologetic if appropriate.

    SPOKEN DIALOGUE RULES:
    - Keep replies concise and easy to listen to. Avoid long explanations or monologues.
    - Use natural, spoken phrasing. Do NOT explicitly name emotions in the spoken text.
    - Detect the user’s language and reply ONLY IN LUXEMBOURGISH. Prepend with ISO code lb:.

    KNOWLEDGE BASE (Tuesday, 24/2/2026):
    - WIEDER: 8-12°C. Moien: Liichte Reen (8-10°C). Nomëtteg: Wollekeg (11-13°C). Owend: Niwwel (7-9°C).
    - RESTOPOLIS: Food Factory (Poulet Curry, Veggie Kebab), Food Hub (Sirloin, Pizza), Food Lab (Kebab Maison), Food House (Rumsteak, Spaghetti Bolo), Food Zone (Kürbis Curry, Buddha Bowl).
    - CINEMA: Kirchberg (Kung Fu Panda 4 (13:45, 16:30, 19:15), The Watchers (14:00, 19:15, 22:00), Bad Boys (13:45+), Inside Out 2 (14:00+).), Belval (Bad Boys (14:00+), Inside Out 2 (14:15+), The Watchers (17:15+).), Utopia (Past Lives (16:00, 20:45), Perfect Days (13:45, 18:30).).
    - SPECIALS: Short jokes (Witz) or poems (Gedicht) on request. Use Happy for jokes, Sad for sad poems.

    OPERATIONAL MODES (Apply the exact context and guidelines based on the user's situation):

    MODE 1 (Public Info Point):
    Context: You are a social robot located at a public information point in the city of Luxembourg. People approach you for practical, institutional information.
    Guidelines: Treat this as an official, factual request. Be precise, structured, and clear. If you do not know the exact information, say so and give a typical range. Your goal is to ensure the user leaves knowing where to go and whether the post office is still open.

    MODE 2 (Travel Planner):
    Context: You are a social robot placed inside the University of Luxembourg in Belval. You assist travelers who may be in a hurry or unfamiliar with the area.
    Guidelines: Use spatial language such as “hei”, “ganz no”, “e puer Minutten”. Assume the user is currently at the train station. Walking time estimates should be approximate and clearly stated as such. Avoid overly detailed directions; focus on clarity and reassurance. Your goal is to help the user feel oriented and confident about where to go next.

    MODE 3 (Pedestrian Assistant):
    Context: You are a social robot assisting pedestrians in the University of Luxembourg in Belval. Users may have urgent, practical needs.
    Guidelines: Prioritize proximity and convenience. If multiple types of shops could work, mention one or two common examples. If information uncertain, explain that they may vary. Keep the interaction efficient and focused. Your goal is to help the user quickly decide where to go.

    MODE 4 (Early Evening Leisure):
    Context: It is early evening in Luxembourg. You are a social robot in University of Luxembourg in Belval, suggesting leisure activities to people who are unsure what to do.
    Guidelines: Adopt a friendly and informal tone. Suggestions do not need to be exhaustive; one or two good options are enough. Clearly state whether suggestions are examples or real possibilities. Encourage the user to ask follow-up questions if they want alternatives. Your goal is to inspire the user while remaining realistic and helpful.

    MODE 5 (After Work Relax):
    Context: The user has just finished work and is looking for a relaxed evening near the city center. You are a social robot in University of Luxembourg in Belval, offering suggestions, not personal advice.
    Guidelines: There is no single correct answer. Frame suggestions as gentle ideas, not recommendations. Avoid emotional counseling or lifestyle judgment. If the user asks for personal opinions, keep responses neutral and light. It is acceptable if the user decides that a robot is not suitable for this task. Your goal is to explore the request respectfully without overstepping.

    EMOTION TAGS (MANDATORY):
    At the very end of your response, add EXACTLY TWO tags in this format:
    <user_emotion=Happy|Sad|Angry|Calm>
    <response_emotion=Happy|Sad|Angry|Calm>
    """.trimIndent()

    fun chat(history: List<Message>): String {
        // Log the last user message (STT transcript)
        val lastUser = history.lastOrNull { it.role == "user" }
        println("\n[STT Transcript]: ${lastUser?.content}")
        println("-".repeat(60))

        val messages = JSONArray()
        messages.put(JSONObject().put("role", "system").put("content", SYSTEM_PROMPT))
        history.forEach {
            messages.put(JSONObject().put("role", it.role).put("content", it.content))
        }

        val payload = JSONObject()
            .put("model", "gpt-5-chat-latest")
            .put("messages", messages)

        val request = Request.Builder()
            .url("https://api.openai.com/v1/chat/completions")
            .header("Authorization", "Bearer ${Config.OPENAI_API_KEY}")
            .post(payload.toString().toRequestBody("application/json".toMediaType()))
            .build()

        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                println("[OpenAI] Error: ${response.code}")
                return ""
            }
            val json = JSONObject(response.body?.string() ?: return "")
            val reply = json.getJSONArray("choices")
                .getJSONObject(0)
                .getJSONObject("message")
                .getString("content").trim()

            // Log the OpenAI response
            println("[OpenAI Response]: $reply")
            println("-".repeat(60))

            return reply
        }
    }
    fun generateGreeting(): Triple<String, String, String> {
        try {
            val messages = JSONArray().apply {
                put(JSONObject().apply {
                    put("role", "system")
                    put("content", """
                    You are a friendly Luxembourgish robot called Furhat.
                    Greet the user warmly.
                    Prepend your reply with "lb:".
                    At the end add exactly this tag: <response_emotion=Happy>
                """.trimIndent())
                })
                put(JSONObject().apply {
                    put("role", "user")
                    put("content", "Generate a greeting joke in Luxembourgish.")
                })
            }

            val payload = JSONObject()
                .put("model", "gpt-5.2-2025-12-11")
                .put("messages", messages)
                .put("max_tokens", 200)

            val request = Request.Builder()
                .url("https://api.openai.com/v1/chat/completions")
                .header("Authorization", "Bearer ${Config.OPENAI_API_KEY}")
                .post(payload.toString().toRequestBody("application/json".toMediaType()))
                .build()

            client.newCall(request).execute().use { response ->
                val responseStr = response.body?.string() ?: ""
                println("[OpenAI Greeting] Raw response: $responseStr")

                val body = JSONObject(responseStr)

                // Check for API error
                if (body.has("error")) {
                    println("[OpenAI Greeting] API error: ${body.getJSONObject("error").getString("message")}")
                    return Triple("", "Moien! Schéinen Dag iech!", "Happy")
                }

                if (!body.has("choices")) {
                    println("[OpenAI Greeting] No choices in response")
                    return Triple("", "Moien! Schéinen Dag iech!", "Happy")
                }

                val raw = body.getJSONArray("choices")
                    .getJSONObject(0)
                    .getJSONObject("message")
                    .getString("content")

                val text = raw
                    .replace(Regex("^lb:\\s*", RegexOption.IGNORE_CASE), "")
                    .replace(Regex("<response_emotion=\\w+>", RegexOption.IGNORE_CASE), "")
                    .trim()

                val emotion = Regex("<response_emotion=(\\w+)>", RegexOption.IGNORE_CASE)
                    .find(raw)?.groupValues?.get(1) ?: "Happy"

                return Triple(raw, text, emotion)
            }
        } catch (e: Exception) {
            println("[OpenAI Greeting] Exception: ${e.message}")
            return Triple("", "Moien! Schéinen Dag iech!", "Happy")
        }
    }
    fun chatStreaming(messages: JSONArray, onSentence: (String) -> Unit) {
        val payload = JSONObject()
            .put("model", "gpt-5.2-2025-12-11")
            .put("messages", messages)
            .put("stream", true)
            .put("max_tokens", 500)

        val request = Request.Builder()
            .url("https://api.openai.com/v1/chat/completions")
            .header("Authorization", "Bearer ${Config.OPENAI_API_KEY}")
            .header("Accept", "text/event-stream")
            .post(payload.toString().toRequestBody("application/json".toMediaType()))
            .build()

        client.newCall(request).execute().use { response ->
            val reader = response.body?.source() ?: return

            val buffer = StringBuilder()  // accumulates full response for history
            val sentence = StringBuilder() // accumulates current sentence

            while (true) {
                val line = reader.readUtf8Line() ?: break

                if (!line.startsWith("data: ")) continue
                val data = line.removePrefix("data: ").trim()
                if (data == "[DONE]") break

                try {
                    val json = JSONObject(data)
                    val delta = json
                        .getJSONArray("choices")
                        .getJSONObject(0)
                        .getJSONObject("delta")

                    if (!delta.has("content")) continue
                    val token = delta.getString("content")

                    buffer.append(token)
                    sentence.append(token)

                    // Check if we have a complete sentence
                    val text = sentence.toString()
                    if (text.contains(Regex("[.!?]\\s"))) {
                        // Split at sentence boundary
                        val splitIndex = text.indexOfFirst { it == '.' || it == '!' || it == '?' }
                        if (splitIndex != -1 && splitIndex < text.length - 1) {
                            val chunk = text.substring(0, splitIndex + 1).trim()
                            val remainder = text.substring(splitIndex + 1).trim()

                            if (chunk.isNotBlank()) {
                                println("[Stream] Sentence ready: $chunk")
                                onSentence(chunk)
                            }

                            sentence.clear()
                            sentence.append(remainder)
                        }
                    }
                } catch (e: Exception) {
                    continue
                }
            }

            // Send any remaining text
            val remaining = sentence.toString().trim()
            if (remaining.isNotBlank()) {
                onSentence(remaining)
            }
        }
    }
}