from PyQt5.Qt import *
from krita import *

import re
import os
import sys
import random
import subprocess

import json

from tempfile import gettempdir

EXTENSION_ID = 'pykrita_restart'
MENU_ENTRY = 'Restart Krita'

class Restart(Extension):
    
    # __init__ runs automatically
    def __init__(self, parent):
        """Initialise plugin"""
        super().__init__(parent)
        # determinate path where to save temp files 
        # prefer a local applicaion directory rather than a /tmp directory
        #paths=QStandardPaths.standardLocations(QStandardPaths.TempLocation)
        
        tempPath=gettempdir() #get temp folder location


        self.__tempPath=os.path.join(gettempdir(), 'restartTemp')

        try:
            os.makedirs(self.__tempPath)
        except FileExistsError:
            # directory already exists
            pass

        
        self.__fileAfterRestart=os.path.join(self.__tempPath, "tempDB.json")
        
        # openeded documents dictionnary 
        self.__docs={}

    def setup(self):
        """Executed at Krita startup, beofre main window is created"""
        # define a trigger, to let plugin reopen document as soon as window is created
        Krita.instance().notifier().windowCreated.connect(self.onWindowCreated)    


    #------------------ the automatic loading function ------------------------
    @pyqtSlot()
    def onWindowCreated(self):
        """Slot executed when Krita window is created"""
        if os.path.isfile(self.__fileAfterRestart):
            # if a file with list of document exists, process it to open documents
            Krita.instance().activeWindow().qwindow().setCursor(Qt.WaitCursor)
            
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
                # trick to set modified() state to True, needed for correct save behaviour
                if file["modified"] is True:
                    doc.setAnnotation("Temp annotation to delete just to set modify state", "temp", b'')
                    doc.removeAnnotation("Temp annotation to delete just to set modify state")
                
                # delete tempfiles
                if file['usetemp'] is True :  
                    os.remove(file["tempfilename"])

            # remove file with list of document (be sure to not reopened it on next "normal" Krita close/start)
            os.remove(self.__fileAfterRestart)
            
            Krita.instance().activeWindow().qwindow().unsetCursor()

    # -------------------------------- restart context menu item -------------------

    def createActions(self, window):
        """Add menu entry for plugin""" 
        action = window.createAction(EXTENSION_ID, MENU_ENTRY, "tools/scripts")
        action.triggered.connect(self.actionRestart)    

    # -------------------------------- restart code --------------------------------
    def actionRestart(self):
        """Execute restart action"""
        # check if documents are opened, and ask for user confirmation
        self.__checkOpenedDocuments()
        
        # -- restart --
        if sys.platform=='win32':
            # running on Windows
            readyToRestart=self.__restartOsWindow()
        elif sys.platform=='linux':
            readyToRestart=self.__restartOsLinux()
        else:
            # need to implement restart process for Linux, MacOS
            readyToRestart=False
        
        if readyToRestart:
            # ok, possible to restart

            # hier muss ich den restart code rein .. aber unwichtiger als der rest
            QApplication.quit()
        else:
            QMessageBox.warning(None, "Restart Krita", "Unable to initialise restart process\nAction cancelled")

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

    def __restartOsWindow(self):
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
        return QProcess.startDetached("cmd", [cmdParameters])

    # -------------------------------- save documents -----------------------
    def __checkOpenedDocuments(self):
        
        self.__docs=[]  # all documents
        numTempDoc=1 #start counting at 1
        
        for doc in Krita.instance().documents():
            # doc not yet saved, produce a tmp filename
            
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
            
            doc.close()

        # write json file
        if len(self.__docs)>0:
            with open(self.__fileAfterRestart, 'w') as file:
                json.dump(self.__docs, file)