package furhatos.app.luxembourgishbot

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.text.SimpleDateFormat
import java.util.*
import javax.mail.*
import javax.mail.internet.*

object InteractionLogger {
    private var session: JSONObject? = null
    private val turns = JSONArray()
    private val dateFormat = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.getDefault())
    private val logDir = File("logs").also { it.mkdirs() }

//    private val participantId = System.getenv("PARTICIPANT_ID") ?: "P_UNKNOWN"
    private val participantId = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.getDefault()).format(Date())
    private val taskId = System.getenv("TASK_ID") ?: "T_UNKNOWN"

    // Email config
    private val fromEmail  = "anonymoususerfurhat@gmail.com"
    private val appPassword = "iftb blef icxg bpqm"
    private val toEmail    = "anonymoususerfurhat@gmail.com"

    fun startSession(asrMode: String, llmBackend: String) {
        session = JSONObject().apply {
            put("session_id", UUID.randomUUID().toString())
            put("participant_id", participantId)
            put("task_id", taskId)
            put("config", JSONObject().apply {
                put("asr_mode", asrMode)
                put("llm_backend", llmBackend)
                put("model", "gpt-5.2-2025-12-11")
            })
            put("start_time", dateFormat.format(Date()))
            put("end_time", JSONObject.NULL)
            put("turns", turns)
            put("summary", JSONObject())
        }
        println("=".repeat(60))
        println("[LOG] Session started — participant=$participantId task=$taskId")
        println("=".repeat(60))
    }

    fun logTurn(
        userText: String,
        userEmotion: String,
        assistantText: String,
        assistantEmotion: String
    ) {
        val turn = JSONObject().apply {
            put("turn_id", UUID.randomUUID().toString())
            put("timestamp", dateFormat.format(Date()))
            put("user", JSONObject().apply {
                put("asr_text", userText)
                put("emotion", userEmotion)
            })
            put("assistant", JSONObject().apply {
                put("response_text", assistantText)
                put("emotion", assistantEmotion)
            })
        }
        turns.put(turn)

        println("\n[User STT]: $userText")
        println("[User Emotion]: $userEmotion")
        println("[Assistant]: $assistantText")
        println("[Assistant Emotion]: $assistantEmotion")
        println("-".repeat(60))
    }

    fun endSession(completed: Boolean = true, notes: String = "") {
        val s = session ?: return

        s.put("end_time", dateFormat.format(Date()))
        s.put("summary", JSONObject().apply {
            put("num_turns", turns.length())
            put("completed", completed)
            put("notes", notes)
        })

        val filename = "${participantId}_task${taskId}_${s.getString("session_id")}.json"
        val file = File(logDir, filename)
        file.writeText(s.toString(2))

        println("\n[LOG] Session ended — ${turns.length()} turns")
        println("[LOG] Saved to ${file.absolutePath}")
        println("=".repeat(60))

        // Send email with log attached
        sendEmail(file)
    }

    private fun sendEmail(logFile: File) {
        try {
            val props = Properties().apply {
                put("mail.smtp.auth", "true")
                put("mail.smtp.starttls.enable", "true")
                put("mail.smtp.host", "smtp.gmail.com")
                put("mail.smtp.port", "587")
            }

            val mailSession = Session.getInstance(props, object : Authenticator() {
                override fun getPasswordAuthentication() =
                    PasswordAuthentication(fromEmail, appPassword)
            })

            val message = MimeMessage(mailSession).apply {
                setFrom(InternetAddress(fromEmail))
                setRecipients(
                    javax.mail.Message.RecipientType.TO,
                    InternetAddress.parse(toEmail)
                )
                subject = "Furhat Session Log — ${logFile.name}"

                val multipart = MimeMultipart()

                val textPart = MimeBodyPart().apply {
                    setText(
                        "Session completed.\n\n" +
                                "Participant: $participantId\n" +
                                "Task: $taskId\n" +
                                "Turns: ${turns.length()}\n\n" +
                                "Full log attached."
                    )
                }

                val attachPart = MimeBodyPart().apply {
                    attachFile(logFile)
                }

                multipart.addBodyPart(textPart)
                multipart.addBodyPart(attachPart)
                setContent(multipart)
            }

            Transport.send(message)
            println("[LOG] Email sent successfully to $toEmail")

        } catch (e: Exception) {
            println("[LOG] Email failed: ${e.message}")
        }
    }
}