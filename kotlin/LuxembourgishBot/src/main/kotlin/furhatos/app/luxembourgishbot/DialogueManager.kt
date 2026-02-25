package furhatos.app.luxembourgishbot

data class Message(val role: String, val content: String)

class DialogueManager {
    private val history = ArrayDeque<Message>()

    fun add(role: String, content: String) {
        history.addLast(Message(role, content))
        while (history.size > Config.MAX_HISTORY) history.removeFirst()
    }

    fun getHistory() = history.toList()
    fun clear() = history.clear()
}