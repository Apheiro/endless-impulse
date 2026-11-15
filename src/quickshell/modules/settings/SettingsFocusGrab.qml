pragma ComponentBehavior: Bound
import QtQuick
import qs.services
import qs.modules.shared.primitives.common

AuthenticationFocusGrab {
    id: root
    required property bool shown
    required property bool authorizing
    signal dismissed()

    // The pre-pkcheck handshake also protects external fallback agents. It is
    // independent of the native agent's actual visible conversation and exit.
    active: shown && !suspended
    suspended: AuthenticationFocusState.active || authorizing
    onCleared: {
        if (!suspended) dismissed();
    }
}
