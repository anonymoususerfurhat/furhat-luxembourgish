package furhatos.app.luxembourgishbot

import furhatos.app.luxembourgishbot.flow.Init
import furhatos.flow.kotlin.Flow
import furhatos.skills.Skill

class LuxembourgishbotSkill : Skill() {
    override fun start() {
        Flow().run(Init)
    }
}

fun main(args: Array<String>) {
    Skill.main(args)
}
