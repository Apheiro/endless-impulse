import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Widgets
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets

SettingsPage {
    forceWidth: true
    property alias installationMap: installationMap
    property alias dependencyMap: dependencyMap
    property alias distroSection: distroSection

    SettingsSection {
        id: distroSection
        objectName: "about-distribution"
        icon: "box"
        title: Translation.tr("Distro")

        RowLayout {
            Layout.alignment: Qt.AlignHCenter
            spacing: 20
            Layout.topMargin: 10
            Layout.bottomMargin: 10
            IconImage {
                implicitSize: 80
                source: IconTheme.iconPath(SystemInfo.logo)
            }
            ColumnLayout {
                Layout.alignment: Qt.AlignVCenter
                // spacing: 10
                StyledText {
                    text: SystemInfo.distroName
                    font.pixelSize: Appearance.font.pixelSize.title
                }
                StyledText {
                    font.pixelSize: Appearance.font.pixelSize.normal
                    text: SystemInfo.homeUrl
                    textFormat: Text.MarkdownText
                    onLinkActivated: (link) => {
                        Qt.openUrlExternally(link)
                    }
                    PointingHandLinkHover {}
                }
            }
        }

        Flow {
            Layout.fillWidth: true
            spacing: 5

            RippleButtonWithIcon {
                materialIcon: "auto_stories"
                mainText: Translation.tr("Documentation")
                onClicked: {
                    Qt.openUrlExternally(SystemInfo.documentationUrl)
                }
            }
            RippleButtonWithIcon {
                materialIcon: "support"
                mainText: Translation.tr("Help & Support")
                onClicked: {
                    Qt.openUrlExternally(SystemInfo.supportUrl)
                }
            }
            RippleButtonWithIcon {
                materialIcon: "bug_report"
                mainText: Translation.tr("Report a Bug")
                onClicked: {
                    Qt.openUrlExternally(SystemInfo.bugReportUrl)
                }
            }
            RippleButtonWithIcon {
                materialIcon: "policy"
                materialIconFill: false
                mainText: Translation.tr("Privacy Policy")
                onClicked: {
                    Qt.openUrlExternally(SystemInfo.privacyPolicyUrl)
                }
            }

        }

    }
    SettingsSection {
        icon: "memory"
        title: "Artificial Impulse"

        StyledText {
            Layout.fillWidth: true
            text: Translation.tr("A fork of illogical-impulse.")
            wrapMode: Text.WordWrap
        }
        RippleButtonWithIcon {
            materialIcon: "code"
            mainText: Translation.tr("Project repository")
            onClicked: Qt.openUrlExternally("https://github.com/Apheiro/dots-hyperland")
        }
    }
    SettingsSection {
        objectName: "about-dependencies"
        icon: "hub"
        title: Translation.tr("Dependency map")
        DependencyMap { id: dependencyMap }
    }
    SettingsSection {
        icon: "account_tree"
        title: Translation.tr("Installation map")
        InstallationMap { id: installationMap }
    }

}
