import qs.modules.shared
import qs.modules.shared.widgets
import QtQuick
import QtQuick.Controls

ListView {
    id: root

    boundsBehavior: Flickable.DragOverBounds

    ScrollBar.vertical: WScrollBar {}

    displaced: Transition {
        animations: [Looks.transition.enter.createObject(this, {
                property: "y"
            })]
    }

}
