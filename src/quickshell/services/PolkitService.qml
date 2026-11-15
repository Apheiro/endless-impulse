pragma Singleton
pragma ComponentBehavior: Bound
import QtQuick
import Quickshell
import Quickshell.Services.Polkit

Singleton {
    id: root
    readonly property var agent: agentLoader.item
    readonly property bool active: agent?.isActive ?? false
    readonly property bool registered: agent?.isRegistered ?? false
    readonly property var flow: agent?.flow ?? null
    readonly property bool conversationActive: registered && active && !!flow && !flow.isCompleted
    readonly property bool interactionAvailable: conversationActive && flow.isResponseRequired
    readonly property string cleanMessage: flow?.message ?? ""
    readonly property string cleanPrompt: (flow?.inputPrompt ?? "").trim() || Translation.tr("Password")
    readonly property string feedback: flow?.supplementaryIsError && flow?.supplementaryMessage
        ? flow.supplementaryMessage
        : flow?.failed ? Translation.tr("Authentication failed. Please try again.")
        : flow?.supplementaryMessage ?? ""
    signal clearInput()

    function cancel() {
        clearInput();
        if (conversationActive) flow.cancelAuthenticationRequest();
    }
    function submit(response) {
        if (interactionAvailable) flow.submit(response);
        clearInput();
    }
    function selectIdentity(identity) {
        clearInput();
        if (conversationActive) flow.selectedIdentity = identity;
    }
    onFlowChanged: {
        clearInput();
        // State only: never log responses, prompts, identities or cookies.
        if (flow) console.debug("Polkit: authentication request started");
    }
    onInteractionAvailableChanged: clearInput()
    onConversationActiveChanged: {
        clearInput();
        // Set synchronously, before presentation takes any keyboard focus.
        if (conversationActive) AuthenticationFocusState.localActive = true;
    }
    Connections {
        target: root.flow
        function onAuthenticationFailed() {
            root.clearInput();
            console.debug("Polkit: authentication rejected; awaiting correction or cancellation");
        }
        function onIsCompletedChanged() {
            if (root.flow?.isCompleted)
                console.debug(root.flow.isSuccessful ? "Polkit: authentication accepted" : "Polkit: authentication ended without authorization");
        }
        function onSelectedIdentityChanged() { root.clearInput(); }
        function onInputPromptChanged() { root.clearInput(); }
        function onResponseVisibleChanged() { root.clearInput(); }
    }
    Loader {
        id: agentLoader
        active: AuthenticationFocusState.owner
        sourceComponent: PolkitAgent {
            id: polkitAgent
            onIsRegisteredChanged: {
                if (!isRegistered) {
                    root.clearInput();
                    console.warn("Polkit: native agent is not registered. Check for a competing session agent; recovery: docs/features/polkit.md");
                }
            }
        }
    }
    Component.onCompleted: {
        if (!registered) console.warn("Polkit: registration pending or failed; inspect Quickshell logs. Explicit fallback: start_polkit_agent.sh --fallback (after stopping the native shell).");
    }
}
