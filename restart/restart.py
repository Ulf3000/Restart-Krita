from PyQt5.Qt import *
from krita import *

import os
import sys
import uuid
import json
import base64


EXTENSION_ID = 'pykrita_restart'
MENU_ENTRY = 'Restart Krita'

AUTOSAVE_INTERVAL_MS = 1 * 60 * 1000  # time in ms  ,   1 * 60 * 1000ms = 60sek = 1min


class Restart(Extension):

    def __init__(self, parent):
        super().__init__(parent)
        self.__autosaveTimer = None
        # guid -> {'tempfilename': str, 'realfilename': str, 'modified': bool, 'thumbnail': str}
        self.__docState = {}

    # ------------------ helpers -----------------------------------------------

    def __newTempPath(self):
        return os.path.join(self.__tempPath, f"tempDoc_{uuid.uuid4().hex}.kra")

    def __docGuid(self, doc):
        existing = bytes(doc.annotation('restart_plugin_guid')).decode('utf-8', errors='')
        if existing:
            return existing
        else:
            is_modified = doc.modified()
            new_guid = uuid.uuid4().hex
            doc.setAnnotation('restart_plugin_guid', 'restart plugin internal id', QByteArray(new_guid.encode()))
            doc.setModified(is_modified)
            return new_guid

    def __docThumbnailB64(self, doc, w=120, h=90):
        try:
            qimg = doc.thumbnail(w, h)
            if qimg is None or qimg.isNull():
                return ''
            buf = QByteArray()
            buf_io = QBuffer(buf)
            buf_io.open(QIODevice.WriteOnly)
            qimg.save(buf_io, 'PNG')
            return base64.b64encode(bytes(buf)).decode('ascii')
        except Exception:
            return ''

    def __saveDoc(self, doc, preserve_modified=False):
        
        # get doc info
        guid = self.__docGuid(doc)
        real_name = doc.fileName()
        is_modified = doc.modified()
        state = self.__docState.get(guid, {}) 

        old_temp = state.get('tempfilename', '') 
        new_temp = self.__newTempPath()
        
        try:
            # update doc state in json
            self.__docState[guid] = {
                'tempfilename': new_temp,
                'realfilename': real_name,
                'modified': is_modified,
                'thumbnail': self.__docThumbnailB64(doc),
            }
            # export, kinda worked better than saving
            doc.exportImage(new_temp, InfoObject())
            # remove old tempfile
            if old_temp and old_temp != new_temp and os.path.isfile(old_temp):
                os.remove(old_temp)
            return True
        except Exception as e:
            print(f"[restart] save failed for '{real_name or 'unsaved'}': {e}") # whatever 🤷‍♂️🤷‍♂️🤷‍♂️ python api sucks 
            return False

    def __removeTempFile(self, tempFile):
        if tempFile and os.path.isfile(tempFile):
            try:
                os.remove(tempFile)
            except OSError:
                pass

    # ------------------ session JSON ------------------------------------------

    def __writeSessionJSON(self):
        entries = list(self.__docState.values())
        if entries:
            with open(self.__fileAfterRestart, 'w') as f:
                json.dump(entries, f)
        elif os.path.isfile(self.__fileAfterRestart):
            os.remove(self.__fileAfterRestart)

    # ------------------ startup -----------------------------------------------
    def onDocumentModified(doc):
        print(f"[restart] documentModified fired: {doc}")

    def setup(self):
        Krita.instance().notifier().windowCreated.connect(self.onWindowCreated)

    @pyqtSlot()
    def onWindowCreated(self):
        krita_resources = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.__tempPath = os.path.join(krita_resources, 'restart_session')
        os.makedirs(self.__tempPath, exist_ok=True)
        self.__fileAfterRestart = os.path.join(self.__tempPath, "tempDB.json")

        notifier = Krita.instance().notifier()
        notifier.setActive(True)
        notifier.imageCreated.connect(self.__onImageCreated)

        

        self.__autosaveTimer = QTimer()
        self.__autosaveTimer.setInterval(AUTOSAVE_INTERVAL_MS)
        self.__autosaveTimer.timeout.connect(self.__autosaveTick)
        self.__autosaveTimer.start()

        if os.path.isfile(self.__fileAfterRestart):
            self.__offerRestore()

    # ------------------ document lifecycle ------------------------------------

    def __onImageCreated(self, doc):
        
        guid = self.__docGuid(doc)
        #if guid in self.__docState:
            #return
        if self.__saveDoc(doc):
            self.__writeSessionJSON()

    # ------------------ autosave tick -----------------------------------------

    @pyqtSlot()
    def __autosaveTick(self):
        live_docs = Krita.instance().documents()
        live_guids = set()

        for doc in live_docs:
            try:
                guid = self.__docGuid(doc)
            except Exception:
                continue
            live_guids.add(guid)
            state = self.__docState.get(guid)
            if state is None:
                self.__saveDoc(doc)
                continue
            state['realfilename'] = doc.fileName()
            self.__saveDoc(doc)

        # only clean up closed docs if at least one doc is still alive
        if live_guids:
            for g in list(self.__docState.keys()):
                if g not in live_guids:
                    state = self.__docState.pop(g)
                    self.__removeTempFile(state.get('tempfilename', ''))

        self.__writeSessionJSON()
    # ------------------ restore -----------------------------------------------

    def __offerRestore(self):
        try:
            with open(self.__fileAfterRestart, 'r') as f:
                files = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            QMessageBox.warning(
                Krita.instance().activeWindow().qwindow(),
                "Restore Session",
                f"Session file could not be read and will be discarded.\n\n{e}"
            )
            os.remove(self.__fileAfterRestart)
            return
        

        # ---- create nice dialog box with thumbnails -----------------------
        dlg = QDialog(Krita.instance().activeWindow().qwindow())
        dlg.setWindowTitle("Restore Session")
        dlg.setMinimumWidth(640)
        layout = QVBoxLayout(dlg)

        label = QLabel(
            f"A session with {len(files)} document(s) was found from a previous run.\n"
            "Do you want to restore it?"
        )
        label.setWordWrap(True)
        layout.addWidget(label)

        THUMB_W, THUMB_H = 120, 90
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        container = QWidget()
        grid = QGridLayout(container)
        grid.setSpacing(8)

        for idx, entry in enumerate(files):
            cell = QWidget()
            cell_layout = QVBoxLayout(cell)
            cell_layout.setContentsMargins(4, 4, 4, 4)
            cell_layout.setSpacing(4)

            thumb_label = QLabel()
            thumb_label.setFixedSize(THUMB_W, THUMB_H)
            thumb_label.setAlignment(Qt.AlignCenter)
            thumb_label.setStyleSheet("background: #1a1a1a; border: 1px solid #444;")
            thumb_b64 = entry.get('thumbnail', '')
            if thumb_b64:
                img_data = base64.b64decode(thumb_b64)
                qimg = QImage()
                qimg.loadFromData(img_data, 'PNG')
                pixmap = QPixmap.fromImage(qimg).scaled(
                    THUMB_W, THUMB_H, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                thumb_label.setPixmap(pixmap)
            else:
                thumb_label.setText("No preview")
            cell_layout.addWidget(thumb_label, 0, Qt.AlignHCenter)

            name = os.path.basename(entry.get('realfilename', '') or 'Unsaved document')
            if entry.get('modified'):
                name = f"{name} (modified)"
            name_label = QLabel(name)
            name_label.setAlignment(Qt.AlignHCenter)
            name_label.setWordWrap(True)
            name_label.setMaximumWidth(THUMB_W + 8)
            if entry.get('modified'):
                name_label.setStyleSheet("color: #f0a000;")
            cell_layout.addWidget(name_label)

            cols = max(1, 640 // (THUMB_W + 32))
            grid.addWidget(cell, idx // cols, idx % cols)

        scroll.setWidget(container)
        scroll.setMaximumHeight(640)
        layout.addWidget(scroll)

        btn_box = QDialogButtonBox(QDialogButtonBox.Yes | QDialogButtonBox.No)
        btn_box.button(QDialogButtonBox.Yes).setText("Restore")
        btn_box.button(QDialogButtonBox.No).setText("Discard")
        btn_box.accepted.connect(dlg.accept)
        btn_box.rejected.connect(dlg.reject)
        layout.addWidget(btn_box)

        if dlg.exec_() != QDialog.Accepted:
            self.__discardSession(files)
            return

        # Remove JSON before opening docs — imageCreated fires during open
        # and would write a new session JSON that we'd then incorrectly delete
        os.remove(self.__fileAfterRestart)
        

        # loading documents begins here -----------------------------
        Krita.instance().activeWindow().qwindow().setCursor(Qt.WaitCursor)
        for file in files:
            try:
                doc = Krita.instance().openDocument(file['tempfilename'])

                if doc is None:
                    print("openDocument returned None — file may be missing or corrupt")
                    continue
                Krita.instance().activeWindow().addView(doc)
                doc.setFileName(file['realfilename'])
                if file['modified']:
                    doc.setModified(True)
            except Exception as e:
                QMessageBox.warning(
                    Krita.instance().activeWindow().qwindow(),
                    "Restore Session",
                    f"Could not restore document:\n{file.get('realfilename') or 'Unsaved document'}\n\n{e}"
                )
            finally:
                self.__removeTempFile(file.get('tempfilename', ''))

        Krita.instance().activeWindow().qwindow().unsetCursor()

    def __discardSession(self, files):
        for file in files:
            self.__removeTempFile(file.get('tempfilename', ''))
        if os.path.isfile(self.__fileAfterRestart):
            os.remove(self.__fileAfterRestart)

    # ------------------ actions -----------------------------------------------

    def createActions(self, window):
        self.actionSaveQuit = window.createAction(
            "pykrita_save_session_quit", "Save Session and Quit", "file"
        )
        self.actionSaveQuit.triggered.connect(self.__actionSaveAndQuit)

        self.actionSaveRestart = window.createAction(
            "pykrita_save_session_restart", "Save Session and Restart", "file"
        )
        self.actionSaveRestart.triggered.connect(self.__actionSaveAndRestart)

    def __flushAllDocs(self):
        for doc in Krita.instance().documents():
            self.__saveDoc(doc, preserve_modified=True)
        self.__writeSessionJSON()

    def __actionSaveAndQuit(self):
        self.__flushAllDocs()
        QApplication.quit()

    def __actionSaveAndRestart(self):
        self.__flushAllDocs()
        if sys.platform == 'win32':
            QProcess.startDetached(sys.executable)
        elif sys.platform == 'linux':
            kritaPid = os.getpid()
            pidCheckCmd = f"ps -p {kritaPid} -o cmd --no-headers"
            kritaPath = os.popen(pidCheckCmd).read().strip()
            os.system(f"sh -c 'while [ $({pidCheckCmd}) ]; do sleep 0.5; done; {kritaPath}&'&")
        QApplication.quit()

    