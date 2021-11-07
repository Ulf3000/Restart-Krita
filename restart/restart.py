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
        if userAnswer==1:
            QApplication.quit()
        else:
            # -- restart --
            if sys.platform=='win32':
                # running on Windows
                self.__restartOsWindows()
            elif sys.platform=='linux':
                self.__restartOsLinux()

        QApplication.quit()


    def __restartOsLinux(self):
        """Linux specific process to restart Krita 
        
        Might be OK on *nix environment...
        """
        kritaPid=os.getpid()
        pidCheckCmd=f"ps -p {kritaPid} -o cmd --no-headers"
        kritaPath=os.popen(pidCheckCmd).read().replace("\n","")
        
        shCmd=f"sh -c 'while [ $({pidCheckCmd}) ]; do sleep 0.5; done; {kritaPath}&'&"
        os.system(shCmd)     

    def __restartOsWindows(self):
        """Windows 10 specific process to restart Krita 
        
        Might be OK on Windows 11, maybe Ok on Windows 7...
        """
        kritaPid=os.getpid()
        kritaPath=sys.executable

        # note: 
        #   following "EncodedCommand":
        #       cABhAHIAYQBtACAAKAANAAoAIAAgAFsAUABhAHIAYQBtAGUAdABlAHIAKABNAGEAbgBkAGEAdABvAHIAeQA9ACQAdAByAHUAZQApAF0AWwBpAG4AdABdACQAawByAGkAdABhAFAAaQBkACwADQAKACAAIABbAFAAYQByAGEAbQBlAHQAZQByACgATQBhAG4AZABhAHQAbwByAHkAPQAkAHQAcgB1AGUAKQBdAFsAcwB0AHIAaQBuAGcAXQAkAGsAcgBpAHQAYQBQAGEAdABoAA0ACgApAA0ACgANAAoAWwBiAG8AbwBsAF0AJABsAG8AbwBwAD0AJABUAHIAdQBlAA0ACgB3AGgAaQBsAGUAKAAkAGwAbwBvAHAAKQAgAHsADQAKACAAIAAgACAAdAByAHkAIAB7AA0ACgAgACAAIAAgACAAIAAgACAAJABwAD0ARwBlAHQALQBQAHIAbwBjAGUAcwBzACAALQBpAGQAIAAkAGsAcgBpAHQAYQBQAGkAZAAgAC0ARQByAHIAbwByAEEAYwB0AGkAbwBuACAAJwBTAHQAbwBwACcADQAKACAAIAAgACAAIAAgACAAIABTAHQAYQByAHQALQBTAGwAZQBlAHAAIAAtAE0AaQBsAGwAaQBzAGUAYwBvAG4AZABzACAANQAwADAADQAKACAAIAAgACAAfQANAAoAIAAgACAAIABjAGEAdABjAGgAIAB7AA0ACgAgACAAIAAgACAAIAAgACAAIwAgAG4AbwB0ACAAZgBvAHUAbgBkAA0ACgAgACAAIAAgACAAIAAgACAAIwAgAGUAeABpAHQAIABsAG8AbwBwAA0ACgAgACAAIAAgACAAIAAgACAAJABsAG8AbwBwAD0AJABGAGEAbABzAGUADQAKACAAIAAgACAAfQANAAoAfQANAAoADQAKAEkAbgB2AG8AawBlAC0ARQB4AHAAcgBlAHMAcwBpAG8AbgAgACQAawByAGkAdABhAFAAYQB0AGgA
        #   is a base64 encoded powershell script
        #   """
        #   param (
        #     [Parameter(Mandatory=$true)][int]$kritaPid,
        #     [Parameter(Mandatory=$true)][string]$kritaPath
        #   )
        #
        #   [bool]$loop=$True
        #   while($loop) {
        #       try {
        #           $p=Get-Process -id $kritaPid -ErrorAction 'Stop'
        #           Start-Sleep -Milliseconds 500
        #       }
        #       catch {
        #           # not found
        #           # exit loop
        #           $loop=$False
        #       }
        #   }
        #
        #   Invoke-Expression $kritaPath
        #   """
        #
        #   ==> recommended: decode Base64 string by yourself to be sure of its content :-P
        #   
        cmdParameters=f"/c powershell -noprofile -ExecutionPolicy bypass -command '{kritaPid}', '{kritaPath}' | powershell -noprofile -ExecutionPolicy bypass -EncodedCommand cABhAHIAYQBtACAAKAANAAoAIAAgAFsAUABhAHIAYQBtAGUAdABlAHIAKABNAGEAbgBkAGEAdABvAHIAeQA9ACQAdAByAHUAZQApAF0AWwBpAG4AdABdACQAawByAGkAdABhAFAAaQBkACwADQAKACAAIABbAFAAYQByAGEAbQBlAHQAZQByACgATQBhAG4AZABhAHQAbwByAHkAPQAkAHQAcgB1AGUAKQBdAFsAcwB0AHIAaQBuAGcAXQAkAGsAcgBpAHQAYQBQAGEAdABoAA0ACgApAA0ACgANAAoAWwBiAG8AbwBsAF0AJABsAG8AbwBwAD0AJABUAHIAdQBlAA0ACgB3AGgAaQBsAGUAKAAkAGwAbwBvAHAAKQAgAHsADQAKACAAIAAgACAAdAByAHkAIAB7AA0ACgAgACAAIAAgACAAIAAgACAAJABwAD0ARwBlAHQALQBQAHIAbwBjAGUAcwBzACAALQBpAGQAIAAkAGsAcgBpAHQAYQBQAGkAZAAgAC0ARQByAHIAbwByAEEAYwB0AGkAbwBuACAAJwBTAHQAbwBwACcADQAKACAAIAAgACAAIAAgACAAIABTAHQAYQByAHQALQBTAGwAZQBlAHAAIAAtAE0AaQBsAGwAaQBzAGUAYwBvAG4AZABzACAANQAwADAADQAKACAAIAAgACAAfQANAAoAIAAgACAAIABjAGEAdABjAGgAIAB7AA0ACgAgACAAIAAgACAAIAAgACAAIwAgAG4AbwB0ACAAZgBvAHUAbgBkAA0ACgAgACAAIAAgACAAIAAgACAAIwAgAGUAeABpAHQAIABsAG8AbwBwAA0ACgAgACAAIAAgACAAIAAgACAAJABsAG8AbwBwAD0AJABGAGEAbABzAGUADQAKACAAIAAgACAAfQANAAoAfQANAAoADQAKAEkAbgB2AG8AawBlAC0ARQB4AHAAcgBlAHMAcwBpAG8AbgAgACQAawByAGkAdABhAFAAYQB0AGgA"
        QProcess.startDetached("cmd", [cmdParameters])
        


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