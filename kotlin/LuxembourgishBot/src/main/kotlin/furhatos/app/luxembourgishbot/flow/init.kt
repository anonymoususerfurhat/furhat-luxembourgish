package furhatos.app.luxembourgishbot.flow

import furhatos.app.luxembourgishbot.flow.main.Idle
import furhatos.app.luxembourgishbot.flow.main.Greeting
import furhatos.app.luxembourgishbot.setting.DISTANCE_TO_ENGAGE
import furhatos.app.luxembourgishbot.setting.MAX_NUMBER_OF_USERS
import furhatos.flow.kotlin.State
import furhatos.flow.kotlin.furhat
import furhatos.flow.kotlin.state
import furhatos.flow.kotlin.users

val Init: State = state {
    init {
        /** Set our default interaction parameters */
        users.setSimpleEngagementPolicy(DISTANCE_TO_ENGAGE, MAX_NUMBER_OF_USERS)
    }
    onEntry {
        /** start interaction */
        when {
            furhat.isVirtual() -> goto(Greeting) // Convenient to bypass the need for user when running Virtual Furhat
            users.hasAny() -> {
                furhat.attend(users.random)
                goto(Greeting)
            }
            else -> goto(Idle)
        }
    }

}
