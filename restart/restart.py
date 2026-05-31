from PyQt5.Qt import *
from krita import *

import os
import sys
import uuid
import json
import base64

EXTENSION_ID = 'pykrita_restart'
MENU_ENTRY = 'Restart Krita'

AUTOSAVE_INTERVAL_MS = 1 * 60 * 1000  # 1 minute


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

    def __saveDoc(self, doc):
        guid = self.__docGuid(doc)
        state = self.__docState.get(guid, {}) 

        old_temp = state.get('tempfilename', '') 
        new_temp = self.__newTempPath()
        
        # Mute our notifier loop so the clone process doesn't trigger secondary events
        try:
            Krita.instance().notifier().imageCreated.disconnect(self.__onImageCreated)
        except Exception:
            pass

        try:
            # Update doc state in database tracking dictionary
            self.__docState[guid] = {
                'tempfilename': new_temp,
                'realfilename': doc.fileName(),
                'modified': doc.modified(),
                'thumbnail': self.__docThumbnailB64(doc),
            }
            
            # Create headless clone to isolate background export execution threads
            clone_doc = doc.clone()
            
            export_properties = InfoObject()
            export_properties.setProperty("compression", 1)
            
            success = clone_doc.exportImage(new_temp, export_properties)
            clone_doc.close()
            
            # Clean up obsolete historical backups safely
            if success and old_temp and old_temp != new_temp and os.path.isfile(old_temp):
                os.remove(old_temp)
            return success

        except Exception as e:
            print(f"[restart] background clone save failed for '{doc.fileName() or 'unsaved'}': {e}")
            return False

        finally:
            # Reconnect active image creation handlers safely
            Krita.instance().notifier().imageCreated.connect(self.__onImageCreated)
    
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
        # Guard clause: ignore invalid, intermediate or headless temporary contexts
        if not doc or doc.fileName() == "":
            return
            
        if self.__saveDoc(doc):
            self.__writeSessionJSON()

    # ------------------ autosave tick -----------------------------------------

    @pyqtSlot()
    def __autosaveTick(self):
        # FIX: Check if the user is actively drawing right now
        # If any mouse/stylus buttons are pressed on the window canvas, defer backup 
        # for 5 seconds to ensure absolute zero brush cursor lag.
        if QApplication.mouseButtons() != Qt.NoButton:
            QTimer.singleShot(5000, self.__autosaveTick)
            return

        live_docs = Krita.instance().documents()
        live_guids = set()

        for doc in live_docs:
            try:
                guid = self.__docGuid(doc)
            except Exception:
                continue
            
            live_guids.add(guid)
            
            # Update path cache parameters gracefully
            state = self.__docState.get(guid)
            if state is not None:
                state['realfilename'] = doc.fileName()
                
            # Single consolidated backup action execution
            self.__saveDoc(doc)

        # Clear tracking data for documents closed out by the user
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

        if not files:
            return

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
                try:
                    img_data = base64.b64decode(thumb_b64)
                    qimg = QImage()
                    qimg.loadFromData(img_data, 'PNG')
                    pixmap = QPixmap.fromImage(qimg).scaled(
                        THUMB_W, THUMB_H, Qt.KeepAspectRatio, Qt.SmoothTransformation
                    )
                    thumb_label.setPixmap(pixmap)
                except Exception:
                    thumb_label.setText("Preview Error")
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

        os.remove(self.__fileAfterRestart)

        # Mute document load listeners during initial parsing loops
        try:
            Krita.instance().notifier().imageCreated.disconnect(self.__onImageCreated)
        except Exception:
            pass

        Krita.instance().activeWindow().qwindow().setCursor(Qt.WaitCursor)
        for file in files:
            try:
                doc = Krita.instance().openDocument(file['tempfilename'])
                if doc is None:
                    continue
                Krita.instance().activeWindow().addView(doc)
                doc.setFileName(file['realfilename'])
                if file['modified']:
                    doc.setModified(True)
            except Exception as e:
                print(f"[restart] Restore failed for file item: {e}")
            finally:
                self.__removeTempFile(file.get('tempfilename', ''))

        Krita.instance().activeWindow().qwindow().unsetCursor()
        
        # Safely re-engage standard event tracking slots
        Krita.instance().notifier().imageCreated.connect(self.__onImageCreated)

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
            self.__saveDoc(doc)
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