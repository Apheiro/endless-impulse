import qs.services
import QtQuick
import Quickshell
import Quickshell.Io
import qs.modules.common
import qs.modules.common.functions

// From https://github.com/caelestia-dots/shell with modifications.
// License: GPLv3

StyledImage {
    id: root
    required property var fileModelData
    asynchronous: true
    fillMode: Image.PreserveAspectFit

    source: {
        if (!fileModelData.fileIsDir)
            return IconTheme.iconPath("application-x-zerosize");

        if ([Directories.documents, Directories.downloads, Directories.music, Directories.pictures, Directories.videos].some(dir => FileUtils.trimFileProtocol(dir) === fileModelData.filePath))
            return IconTheme.iconPath(`folder-${fileModelData.fileName.toLowerCase()}`);

        return IconTheme.iconPath("inode-directory");
    }

    onStatusChanged: {
        if (status === Image.Error)
            source = IconTheme.iconPath("error");
    }

    Process {
        running: !fileModelData.fileIsDir
        command: ["file", "--mime", "-b", fileModelData.filePath]
        stdout: StdioCollector {
            onStreamFinished: {
                const mime = text.split(";")[0].replace("/", "-");
                root.source = Images.validImageTypes.some(t => mime === `image-${t}`) ? fileModelData.fileUrl : IconTheme.iconPath(mime, "image-missing");
            }
        }
    }
}
