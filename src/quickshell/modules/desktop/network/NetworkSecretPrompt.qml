pragma ComponentBehavior: Bound
import qs.modules.shared.primitives.common
import QtQuick
import QtQuick.Layouts
import qs.services
import qs.modules.shared
import qs.modules.shared.widgets

ColumnLayout {
    id:root
    Layout.fillWidth:true
    spacing:8
    StyledText{Layout.fillWidth:true;text:NetworkControl.prompt.name||"";textFormat:Text.PlainText;font.weight:Font.DemiBold}
    StyledText{Layout.fillWidth:true;text:Translation.tr("NetworkManager needs credentials to finish connecting.");wrapMode:Text.WordWrap;color:Appearance.colors.colSubtext}
    Repeater {
        id:fields
        model:NetworkControl.prompt.fields||[]
        delegate:MaterialTextField { required property string modelData;Layout.fillWidth:true;wrapMode:TextInput.NoWrap;echoMode:TextInput.Password;placeholderText:modelData;Component.onCompleted:forceActiveFocus() }
    }
    RowLayout {
        RippleButtonWithIcon{materialIcon:"close";mainText:Translation.tr("Cancel");onClicked:NetworkControl.respond(false,{})}
        RippleButtonWithIcon{materialIcon:"check";mainText:Translation.tr("Connect");onClicked:{const values={};for(let i=0;i<fields.count;i++){const field=fields.itemAt(i);values[field.modelData]=field.text;field.text="";}NetworkControl.respond(true,values);}}
    }
}
