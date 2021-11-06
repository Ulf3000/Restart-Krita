from PyQt5.Qt import *
from krita import *
from tempfile import gettempdir

import os
import sys

import random
import json


EXTENSION_ID = 'pykrita_restart'
MENU_ENTRY = 'Restart Krita'

class Restart(Extension):
    
    # __init__ runs automatically
    def __init__(self, parent):
        """Initialise plugin"""
        super().__init__(parent)

        tempPath=gettempdir() 
        self.__tempPath=os.path.join(gettempdir(), 'Krita_restart_temp')
        try:
            os.makedirs(self.__tempPath)
        except FileExistsError:
            pass
        self.__fileAfterRestart=os.path.join(self.__tempPath, "tempDB.json")
        
    def setup(self):
        """Executed at Krita startup, beofre main window is created"""
        # define a trigger, to let plugin reopen document as soon as window is created
        Krita.instance().notifier().windowCreated.connect(self.onWindowCreated)    


    #------------------ the automatic loading function ------------------------
    @pyqtSlot()
    def onWindowCreated(self):
        """Slot executed when Krita window is created"""
        if os.path.isfile(self.__fileAfterRestart):
            
            Krita.instance().activeWindow().qwindow().setCursor(Qt.WaitCursor)

            # if a file with list of document exists, process it to open documents
            with open(self.__fileAfterRestart, 'r') as file:
                files = json.load(file)

            for file in files:
                # open document and attach it to current window
                docName=''
                if file['usetemp'] is True :
                    docName=file["tempfilename"]
                else:                                   
                    docName=file["realfilename"]
                                    
                doc=Krita.instance().openDocument(docName)
                Krita.instance().activeWindow().addView(doc)

                doc.setFileName(file["realfilename"])
                # trick to set modified() state to True, needed for correct save behaviour after the restart/reload
                if file["modified"] is True:
                    doc.setAnnotation("Temp annotation to delete just to set modify state", "temp", b'')
                    doc.removeAnnotation("Temp annotation to delete just to set modify state")
                
                # delete tempfiles
                if file['usetemp'] is True :  
                    os.remove(file["tempfilename"])

            # remove file with list of documents to be sure to not reopened it on next "normal" Krita close/start)
            os.remove(self.__fileAfterRestart)
            
            Krita.instance().activeWindow().qwindow().unsetCursor()

    # -------------------------------- restart context menu item -------------------

    def createActions(self, window):
        """Add menu entry for plugin""" 
        action = window.createAction(EXTENSION_ID, MENU_ENTRY, "tools/scripts")
        action.triggered.connect(self.actionRestart)    

    # -------------------------------- restart code --------------------------------
    def actionRestart(self):
        
        self.saveTempDocuments() # check if documents are opened, and save them for restart

        msgBox = QMessageBox()
        msgBox.setText('Restart right now??? Or prepare Document-Reload for next manual startup?')
        msgBox.addButton(QPushButton('RESTART NOW'), QMessageBox.YesRole)
        msgBox.addButton(QPushButton('PREPARE RELOAD'), QMessageBox.NoRole)

        userAnswer = msgBox.exec_()
        if userAnswer==QMessageBox.No:
            QApplication.quit()
        else:
            # -- restart --
            if sys.platform=='win32':
                os.execl(sys.executable,"dummy_argument") /need at least one argument so just set a dummy argument
            elif sys.platform=='linux':
                readyToRestart=self.__restartOsLinux()
        
    def __restartOsLinux(self):
        """Linux specific process to restart Krita 
        
        Might be OK on *nix environment...
        """
        kritaPid=os.getpid()
        pidCheckCmd=f"ps -p {kritaPid} -o cmd --no-headers"
        kritaPath=os.popen(pidCheckCmd).read().replace("\n","")
        
        shCmd=f"sh -c 'while [ $({pidCheckCmd}) ]; do sleep 0.5; done; {kritaPath}&'&"
        os.system(shCmd)
        
        return True

    # -------------------------------- save documents -----------------------
    def saveTempDocuments(self):
        
        self.__docs=[]
        numTempDoc=1 #start counting at 1
        
        for doc in Krita.instance().documents():
            
            if doc.fileName()=='' or doc.modified() is True: # if modified or unsaved use tempfile otherwise use real file
                
                tempDocFileName = f"tempDocToDelete_{numTempDoc:04}_{random.randint(1,999999):06}.kra"
                tempFileName=os.path.join(self.__tempPath, tempDocFileName)

                self.__docs.append({
                    'tempfilename': tempFileName,
                    'realfilename': doc.fileName(),
                    'modified': doc.modified(),
                    'usetemp': True
                })
                doc.setFileName(tempFileName)
                doc.save()
            else:
                self.__docs.append({
                    'tempfilename': '',
                    'realfilename': doc.fileName(),
                    'modified': doc.modified(),
                    'usetemp': False
                })

        # write json file
        if len(self.__docs)>0:
            with open(self.__fileAfterRestart, 'w') as file:
                json.dump(self.__docs, file)