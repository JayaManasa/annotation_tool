import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import os
import json


class BoundingBox:
    """Class to represent a bounding box"""
    CLASSIFICATIONS = {
        'M': 'Macula',
        'H': 'Hemorrhages',
        'D': 'Disc',
        'A': 'Microaneurysms',
        'C': 'Cotton Wool Spots',
        'F': 'Fovea',
        'E': 'Hard Exudates',
        'L': 'Laser marks',
        'N': 'NVD NVE',
        'V': 'Vitreous hemorrhage',
        'O': 'Other'
    }

    def __init__(self, x1, y1, x2, y2, canvasid=None):
        self.x1 = min(x1, x2)
        self.y1 = min(y1, y2)
        self.x2 = max(x1, x2)
        self.y2 = max(y1, y2)
        self.canvasid = canvasid
        self.selected = False
        self.classification = None

    def get_coords(self):
        return self.x1, self.y1, self.x2, self.y2

    def contains_point(self, x, y):
        # IMPROVED: Added margin for easier selection
        margin = 5
        return (self.x1 - margin) <= x <= (self.x2 + margin) and (self.y1 - margin) <= y <= (self.y2 + margin)

    def get_color(self):
        """Get color based on classification"""
        if self.classification:
            colors = {'M': 'yellow', 'H': 'red', 'D': 'blue', 'A': 'green', 'C': 'orange', 'F': 'cyan',
                      'E': 'magenta', 'L': 'purple', 'N': 'pink', 'V': 'brown', 'O': 'gray'}
            return colors.get(self.classification, 'blue')
        return 'blue'

    def get_classification_name(self):
        return self.CLASSIFICATIONS.get(self.classification, 'Unclassified')


class ImageViewer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Joly AI Image Annotator")
        self.geometry("1600x900")
        self.configure(bg='white')

        # UI Elements
        self.filelistbox = None
        self.filenamelabel = None
        self.imagecanvas = None
        self.magnifiercanvas = None
        self.magnifierlabel = None
        self.selectedfolder = None
        self.currentimage = None
        self.currentindex = -1
        self.originalimage = None
        self.displayscale = 1.0
        self.imageoffsetx = 0
        self.imageoffsety = 0

        # Magnifier settings
        self.magnifierzoom = 3.0
        self.magnifiersize = 400
        self.magnifiedimage = None

        # Bounding box management
        self.boundingboxes = []
        self.drawingbox = False
        self.startx = 0
        self.starty = 0
        self.currentboxid = None
        self.selectedbox = None
        self.pendingclassification = None
        self.classificationmode = False
        self.instructionlabel = None

        # ADDED: Context menu for bounding boxes
        self.contextmenu = None

        self.imageextensions = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ppm', '.pgm', '.pbm')
        self.createtopnavbar()
        self.createcontainerframe()
        self.createcontextmenu()  # ADDED: Create context menu
        self.bindcanvasevents()
        self.bindkeyboardevents()

    def createtopnavbar(self):
        buttonframe = tk.Frame(self, bg='white')
        buttonframe.pack(side=tk.TOP, fill='x', anchor='w', pady=5)

        btnselect = tk.Button(buttonframe, text="Select Folder", command=self.selectfolder)
        btnright = tk.Button(buttonframe, text="Next >", command=self.nextimage)
        btnleft = tk.Button(buttonframe, text="< Previous", command=self.previousimage)

        btnclearboxes = tk.Button(buttonframe, text="Clear All Boxes", command=self.clearallboxes, bg='#ffcccc')
        btndeleteselected = tk.Button(buttonframe, text="Delete Selected", command=self.deleteselectedbox, bg='#ffdddd')
        btnsave = tk.Button(buttonframe, text="Save Annotations", command=self.savecurrentannotations, bg='#ccffcc')

        btnzoomin = tk.Button(buttonframe, text="Zoom+ Magnifier", command=self.increasemagnifierzoom, bg='#e6f2ff')
        btnzoomout = tk.Button(buttonframe, text="Zoom- Magnifier", command=self.decreasemagnifierzoom, bg='#e6f2ff')

        # ADDED: Status label for annotation count
        self.statuslabel = tk.Label(buttonframe, text="Annotations: 0", font=('Arial', 10), bg='white')

        btnsave.pack(side=tk.LEFT, padx=10, pady=5)
        btnselect.pack(side=tk.LEFT, padx=10, pady=(10, 0))
        btnclearboxes.pack(side=tk.LEFT, padx=10, pady=5)
        btndeleteselected.pack(side=tk.LEFT, padx=10, pady=5)
        btnzoomin.pack(side=tk.LEFT, padx=5, pady=5)
        btnzoomout.pack(side=tk.LEFT, padx=5, pady=5)
        self.statuslabel.pack(side=tk.LEFT, padx=20, pady=5)  # ADDED
        btnright.pack(side=tk.RIGHT, padx=10, pady=5)
        btnleft.pack(side=tk.RIGHT, padx=10, pady=5)

    # ADDED: Create context menu
    def createcontextmenu(self):
        """Create right-click context menu for bounding boxes"""
        self.contextmenu = tk.Menu(self, tearoff=0)
        self.contextmenu.add_command(label="Delete This Box", command=self.deleteselectedbox)
        self.contextmenu.add_command(label="Reclassify", command=self.reclassifybox)
        self.contextmenu.add_separator()
        self.contextmenu.add_command(label="Show Info", command=self.showboxinfo)
        self.contextmenu.add_command(label="Cancel", command=lambda: self.contextmenu.unpost())

    def createcontainerframe(self):
        container = tk.Frame(self, bg='white')
        container.pack(fill=tk.BOTH, expand=True)

        # Left pane: 15% file list
        leftpane = tk.Frame(container, bg='white')
        leftpane.place(relx=0, rely=0, relwidth=0.15, relheight=1)
        tk.Label(leftpane, text="Files", bg='white').pack(padx=10, pady=(10, 5))
        self.filelistbox = tk.Listbox(leftpane, bg='white')
        self.filelistbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.filelistbox.bind('<<ListboxSelect>>', self.onfileselect)

        # Middle pane: 65% image display
        middlepane = tk.Frame(container, bg='white')
        middlepane.place(relx=0.15, rely=0, relwidth=0.65, relheight=1)
        self.filenamelabel = tk.Label(middlepane, text="Select an image to view", font=('Arial', 12), bg='white')
        self.filenamelabel.pack(padx=10, pady=10)

        self.imagecanvas = tk.Canvas(middlepane, bg='white', highlightthickness=0)
        self.imagecanvas.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Right pane: 20% magnifier panel
        rightpane = tk.Frame(container, bg='lightgray', relief=tk.RAISED, bd=2)
        rightpane.place(relx=0.75, rely=0, relwidth=0.25, relheight=1)
        tk.Label(rightpane, text="Magnifier", font=('Arial', 12, 'bold'), bg='lightgray').pack(pady=(10, 5))
        self.magnifiercanvas = tk.Canvas(rightpane, bg='white', width=self.magnifiersize, height=self.magnifiersize)
        self.magnifiercanvas.pack(pady=5)
        self.magnifierlabel = tk.Label(rightpane, text="Move cursor over image", font=('Arial', 10), bg='lightgray')
        self.magnifierlabel.pack(pady=5)

        self.zoomfactorlabel = tk.Label(rightpane, text=f"Zoom: {self.magnifierzoom}x", font=('Arial', 10),
                                        bg='lightgray')
        self.zoomfactorlabel.pack(pady=5)

        # ADDED: Annotation list in right pane
        tk.Label(rightpane, text="Annotations", font=('Arial', 12, 'bold'), bg='lightgray').pack(pady=(20, 5))
        self.annotationlistbox = tk.Listbox(rightpane, bg='white', height=10)
        self.annotationlistbox.pack(pady=5, padx=10, fill=tk.BOTH, expand=True)
        self.annotationlistbox.bind('<Double-Button-1>', self.selectannotationfromlist)
        self.annotationlistbox.bind('<Button-3>', self.showcontextmenuforlist)

    def bindcanvasevents(self):
        """Bind mouse events for bounding box functionality"""
        self.imagecanvas.bind('<Button-1>', self.oncanvasclick)
        self.imagecanvas.bind('<B1-Motion>', self.oncanvasdrag)
        self.imagecanvas.bind('<ButtonRelease-1>', self.oncanvasrelease)
        self.imagecanvas.bind('<Button-3>', self.onrightclick)  # Right-click for context menu
        self.imagecanvas.bind('<Motion>', self.onmousemove)

    def bindkeyboardevents(self):
        """Bind keyboard events for arrow key navigation"""
        self.bind('<Left>', lambda e: self.previousimage())
        self.bind('<Right>', lambda e: self.nextimage())
        self.bind('<Delete>', lambda e: self.deleteselectedbox())
        self.bind('<BackSpace>', lambda e: self.deleteselectedbox())

        self.bind('m', lambda e: self.classifybox('M'))
        self.bind('M', lambda e: self.classifybox('M'))
        self.bind('h', lambda e: self.classifybox('H'))
        self.bind('H', lambda e: self.classifybox('H'))
        self.bind('d', lambda e: self.classifybox('D'))
        self.bind('D', lambda e: self.classifybox('D'))
        self.bind('a', lambda e: self.classifybox('A'))
        self.bind('A', lambda e: self.classifybox('A'))
        self.bind('c', lambda e: self.classifybox('C'))
        self.bind('C', lambda e: self.classifybox('C'))
        self.bind('f', lambda e: self.classifybox('F'))
        self.bind('F', lambda e: self.classifybox('F'))
        self.bind('e', lambda e: self.classifybox('E'))
        self.bind('E', lambda e: self.classifybox('E'))
        self.bind('l', lambda e: self.classifybox('L'))
        self.bind('L', lambda e: self.classifybox('L'))
        self.bind('n', lambda e: self.classifybox('N'))
        self.bind('N', lambda e: self.classifybox('N'))
        self.bind('v', lambda e: self.classifybox('V'))
        self.bind('V', lambda e: self.classifybox('V'))
        self.bind('o', lambda e: self.classifybox('O'))
        self.bind('O', lambda e: self.classifybox('O'))
        self.focus_set()

    def onmousemove(self, event):
        """Handle mouse movement to update magnifier"""
        if not self.originalimage:
            return
        canvasx, canvasy = event.x, event.y

        origx = (canvasx - self.imageoffsetx) / self.displayscale
        origy = (canvasy - self.imageoffsety) / self.displayscale

        imgwidth, imgheight = self.originalimage.size
        if origx < 0 or origx > imgwidth or origy < 0 or origy > imgheight:
            self.magnifierlabel.config(text="Cursor outside image")
            return

        try:
            cropsize = self.magnifiersize // self.magnifierzoom
            left = max(0, int(origx - cropsize // 2))
            top = max(0, int(origy - cropsize // 2))
            right = min(imgwidth, int(origx + cropsize // 2))
            bottom = min(imgheight, int(origy + cropsize // 2))

            cropped = self.originalimage.crop((left, top, right, bottom))
            magnified = cropped.resize((self.magnifiersize, self.magnifiersize), Image.Resampling.NEAREST)
            self.magnifiedimage = ImageTk.PhotoImage(magnified)

            self.magnifiercanvas.delete('all')
            self.magnifiercanvas.create_image(0, 0, anchor=tk.NW, image=self.magnifiedimage)

            center = self.magnifiersize // 2
            self.magnifiercanvas.create_line(center - 10, center, center + 10, center, fill='red', width=2)
            self.magnifiercanvas.create_line(center, center - 10, center, center + 10, fill='red', width=2)

            self.magnifierlabel.config(text=f"Magnified at ({int(origx)}, {int(origy)})")
        except Exception as e:
            pass

    def increasemagnifierzoom(self):
        """Increase magnifier zoom factor"""
        self.magnifierzoom = min(10.0, self.magnifierzoom + 0.5)
        self.zoomfactorlabel.config(text=f"Zoom: {self.magnifierzoom}x")

    def decreasemagnifierzoom(self):
        """Decrease magnifier zoom factor"""
        self.magnifierzoom = max(1.0, self.magnifierzoom - 0.5)
        self.zoomfactorlabel.config(text=f"Zoom: {self.magnifierzoom}x")

    def selectfolder(self):
        folderselected = filedialog.askdirectory()
        if folderselected:
            self.selectedfolder = folderselected
            self.displayfilesinfolder(folderselected)
        else:
            messagebox.showinfo("No Selection", "No folder selected!")

    def displayfilesinfolder(self, folderpath):
        files = [f for f in os.listdir(folderpath) if
                 os.path.isfile(os.path.join(folderpath, f)) and f.lower().endswith(self.imageextensions)]
        files.sort()
        self.filelistbox.delete(0, tk.END)
        for file in files:
            self.filelistbox.insert(tk.END, file)
        self.currentindex = -1
        if files:
            self.selectimagebyindex(0)

    def onfileselect(self, event):
        """Handle manual selection from listbox"""
        selectedindices = self.filelistbox.curselection()
        if selectedindices:
            self.currentindex = selectedindices[0]
            filename = self.filelistbox.get(self.currentindex)
            self.filenamelabel.config(text=filename)
            self.displayimage(filename)

    def selectimagebyindex(self, index):
        """Select image by index and update display"""
        totalfiles = self.filelistbox.size()
        if totalfiles == 0:
            return
        if index < 0:
            index = 0
        elif index >= totalfiles:
            index = totalfiles - 1
        self.currentindex = index
        self.filelistbox.selection_clear(0, tk.END)
        self.filelistbox.selection_set(index)
        self.filelistbox.activate(index)
        self.filelistbox.see(index)
        filename = self.filelistbox.get(index)
        self.filenamelabel.config(text=filename)
        self.displayimage(filename)

    def previousimage(self):
        """Navigate to previous image"""
        if self.currentindex >= 0:
            currentfilename = self.filelistbox.get(self.currentindex)
            self.saveannotations(currentfilename)
        if self.filelistbox.size() == 0:
            messagebox.showinfo("Info", "No images loaded!")
            return
        newindex = self.currentindex - 1
        if newindex < 0:
            newindex = self.filelistbox.size() - 1
        self.selectimagebyindex(newindex)

    def nextimage(self):
        """Navigate to next image"""
        if self.currentindex >= 0:
            currentfilename = self.filelistbox.get(self.currentindex)
            self.saveannotations(currentfilename)
        if self.filelistbox.size() == 0:
            messagebox.showinfo("Info", "No images loaded!")
            return
        newindex = self.currentindex + 1
        if newindex >= self.filelistbox.size():
            newindex = 0
        self.selectimagebyindex(newindex)

    def displayimage(self, filename):
        """Display image on canvas and clear existing bounding boxes"""
        if not self.selectedfolder:
            return
        imagepath = os.path.join(self.selectedfolder, filename)
        try:
            self.originalimage = Image.open(imagepath)
            self.imagecanvas.delete('all')
            self.imagecanvas.update_idletasks()
            canvaswidth = self.imagecanvas.winfo_width()
            canvasheight = self.imagecanvas.winfo_height()
            if canvaswidth <= 1 or canvasheight <= 1:
                canvaswidth = 800
                canvasheight = 600
            imgwidth, imgheight = self.originalimage.size
            scalew = canvaswidth / imgwidth
            scaleh = canvasheight / imgheight
            self.displayscale = min(scalew, scaleh, 1.0)
            newwidth = int(imgwidth * self.displayscale)
            newheight = int(imgheight * self.displayscale)
            self.imageoffsetx = (canvaswidth - newwidth) // 2
            self.imageoffsety = (canvasheight - newheight) // 2
            imgresized = self.originalimage.resize((newwidth, newheight), Image.Resampling.LANCZOS)
            self.currentimage = ImageTk.PhotoImage(imgresized)
            self.imagecanvas.create_image(self.imageoffsetx, self.imageoffsety, anchor=tk.NW, image=self.currentimage)
            self.loadannotations(filename)
        except Exception as e:
            messagebox.showerror("Error", f"Could not load image: {str(e)}")

    def oncanvasclick(self, event):
        """Handle canvas click - start drawing bounding box or select existing"""
        # IMPROVED: Check if clicking on existing box first
        clickedbox = self.findboxatpoint(event.x, event.y)
        if clickedbox:
            # Select the box instead of starting new drawing
            self.deselectallboxes()
            self.selectedbox = clickedbox
            clickedbox.selected = True
            self.imagecanvas.itemconfig(clickedbox.canvasid, outline='green', width=3)
            self.updateannotationlist()
            return

        # Start drawing new box
        self.deselectallboxes()
        self.startx = event.x
        self.starty = event.y
        self.drawingbox = True

    def findboxatpoint(self, x, y):
        """Find bounding box at given point"""
        for bbox in reversed(self.boundingboxes):  # Check from top to bottom
            if bbox.contains_point(x, y):
                return bbox
        return None

    def oncanvasdrag(self, event):
        """Handle canvas drag - update bounding box preview"""
        if self.drawingbox:
            if self.currentboxid:
                self.imagecanvas.delete(self.currentboxid)
            self.currentboxid = self.imagecanvas.create_rectangle(self.startx, self.starty, event.x, event.y,
                                                                  outline='red', width=2)
            self.updatemagnifier(event.x, event.y)

    def updatemagnifier(self, canvasx, canvasy):
        """Update magnifier with current cursor position"""
        self.onmousemove(type('Event', (), {'x': canvasx, 'y': canvasy})())

    def oncanvasrelease(self, event):
        """Handle mouse release - finalize bounding box"""
        if self.drawingbox:
            self.drawingbox = False
            if abs(event.x - self.startx) > 5 and abs(event.y - self.starty) > 5:
                if self.currentboxid:
                    self.imagecanvas.delete(self.currentboxid)
                bbox = BoundingBox(self.startx, self.starty, event.x, event.y)
                self.boundingboxes.append(bbox)
                self.pendingclassification = bbox
                self.classificationmode = True
                canvasid = self.imagecanvas.create_rectangle(self.startx, self.starty, event.x, event.y,
                                                             outline='orange', width=3, tags=bbox)
                bbox.canvasid = canvasid
                self.showclassificationinstruction()
            if self.currentboxid:
                self.imagecanvas.delete(self.currentboxid)
                self.currentboxid = None
            self.updatemagnifier(event.x, event.y)

    def onrightclick(self, event):
        """Handle right click - show context menu for bounding box"""
        clickedbox = self.findboxatpoint(event.x, event.y)

        self.deselectallboxes()

        if clickedbox:
            self.selectedbox = clickedbox
            clickedbox.selected = True
            self.imagecanvas.itemconfig(clickedbox.canvasid, outline='green', width=3)
            self.updateannotationlist()

            # IMPROVED: Show context menu at cursor position
            try:
                self.contextmenu.tk_popup(event.x_root, event.y_root, 0)
            finally:
                self.contextmenu.grab_release()

    # ADDED: Select annotation from list
    def selectannotationfromlist(self, event):
        """Double-click on annotation list to select box"""
        selection = self.annotationlistbox.curselection()
        if selection:
            index = selection[0]
            if index < len(self.boundingboxes):
                self.deselectallboxes()
                self.selectedbox = self.boundingboxes[index]
                self.selectedbox.selected = True
                self.imagecanvas.itemconfig(self.selectedbox.canvasid, outline='green', width=3)

    # ADDED: Show context menu for list
    def showcontextmenuforlist(self, event):
        """Right-click on annotation list to show context menu"""
        selection = self.annotationlistbox.curselection()
        if selection:
            index = selection[0]
            if index < len(self.boundingboxes):
                self.deselectallboxes()
                self.selectedbox = self.boundingboxes[index]
                self.selectedbox.selected = True
                self.imagecanvas.itemconfig(self.selectedbox.canvasid, outline='green', width=3)
                try:
                    self.contextmenu.tk_popup(event.x_root, event.y_root, 0)
                finally:
                    self.contextmenu.grab_release()

    # ADDED: Reclassify selected box
    def reclassifybox(self):
        """Reclassify the selected bounding box"""
        if self.selectedbox:
            self.pendingclassification = self.selectedbox
            self.classificationmode = True
            self.showclassificationinstruction()

    # ADDED: Show box info
    def showboxinfo(self):
        """Show information about selected bounding box"""
        if self.selectedbox:
            origx1 = (self.selectedbox.x1 - self.imageoffsetx) / self.displayscale
            origy1 = (self.selectedbox.y1 - self.imageoffsety) / self.displayscale
            origx2 = (self.selectedbox.x2 - self.imageoffsetx) / self.displayscale
            origy2 = (self.selectedbox.y2 - self.imageoffsety) / self.displayscale
            width = abs(origx2 - origx1)
            height = abs(origy2 - origy1)

            info = f"Classification: {self.selectedbox.get_classification_name()}\n"
            info += f"Coordinates: ({int(origx1)}, {int(origy1)}) to ({int(origx2)}, {int(origy2)})\n"
            info += f"Size: {int(width)} x {int(height)} pixels"

            messagebox.showinfo("Bounding Box Info", info)

    def deselectallboxes(self):
        """Deselect all bounding boxes"""
        for bbox in self.boundingboxes:
            if bbox.selected:
                bbox.selected = False
                color = bbox.get_color() if bbox.classification else 'blue'
                self.imagecanvas.itemconfig(bbox.canvasid, outline=color, width=2)
        self.selectedbox = None
        self.updateannotationlist()

    def clearallboxes(self):
        """Clear all bounding boxes"""
        # IMPROVED: Ask for confirmation
        if self.boundingboxes:
            result = messagebox.askyesno("Confirm", f"Delete all {len(self.boundingboxes)} annotations?")
            if not result:
                return

        for bbox in self.boundingboxes:
            if bbox.canvasid:
                self.imagecanvas.delete(bbox.canvasid)
        self.boundingboxes.clear()
        self.selectedbox = None
        self.updateannotationlist()
        self.updatestatusbar()

    def deleteselectedbox(self):
        """Delete the currently selected bounding box"""
        if self.selectedbox:
            # IMPROVED: Optional confirmation
            # result = messagebox.askyesno("Confirm", "Delete this annotation?")
            # if not result:
            #     return

            self.imagecanvas.delete(self.selectedbox.canvasid)
            self.boundingboxes.remove(self.selectedbox)
            self.selectedbox = None
            self.updateannotationlist()
            self.updatestatusbar()
            print("Deleted selected annotation")

    # ADDED: Update annotation list
    def updateannotationlist(self):
        """Update the annotation listbox"""
        self.annotationlistbox.delete(0, tk.END)
        for i, bbox in enumerate(self.boundingboxes):
            classname = bbox.get_classification_name() if bbox.classification else "Unclassified"
            displaytext = f"{i + 1}. {classname}"
            if bbox.selected:
                displaytext += " (Selected)"
            self.annotationlistbox.insert(tk.END, displaytext)

            color = bbox.get_color() if bbox.classification else 'white'
            self.annotationlistbox.itemconfig(i, {'fg': color})
            if bbox.selected:
                self.annotationlistbox.itemconfig(i, {'bg': 'darkgray'})
                self.annotationlistbox.selection_set(i)
            else:
                self.annotationlistbox.itemconfig(i, {'bg': 'black'})
        self.updatestatusbar()

    # ADDED: Update status bar
    def updatestatusbar(self):
        """Update status label with annotation count"""
        classified = len([b for b in self.boundingboxes if b.classification])
        total = len(self.boundingboxes)
        self.statuslabel.config(text=f"Annotations: {classified}/{total} classified")

    def showclassificationinstruction(self):
        """Show classification instruction to user"""
        instructiontext = "Classify: M(Macula), H(Hemorrhages), D(Disc), A(Microaneurysms), C(Cotton Wool Spots), F(Fovea), E(Hard Exudates), L(Laser marks), N(NVD NVE), V(Vitreous hemorrhage), O(Other) "

        if self.instructionlabel is None:
            self.instructionlabel = tk.Label(
                self,
                text=instructiontext,
                bg='yellow',
                fg='black',
                font=('Arial', 10, 'bold')
            )
        else:
            self.instructionlabel.config(text=instructiontext)
        self.instructionlabel.pack(side=tk.BOTTOM, fill='x')

    def hideclassificationinstruction(self):
        """Hide classification instruction"""
        if self.instructionlabel is not None:
            self.instructionlabel.pack_forget()

    def classifybox(self, classificationkey):
        """Classify the pending bounding box"""
        if (hasattr(self, 'pendingclassification') and self.pendingclassification and
                hasattr(self, 'classificationmode') and self.classificationmode):
            self.pendingclassification.classification = classificationkey
            color = self.pendingclassification.get_color()
            self.imagecanvas.itemconfig(self.pendingclassification.canvasid, outline=color, width=2)
            self.pendingclassification = None
            self.classificationmode = False
            if hasattr(self, 'hideclassificationinstruction'):
                self.hideclassificationinstruction()
            self.updateannotationlist()
            print(f"Box classified as {classificationkey}")

    def cleanupunclassifiedboxes(self):
        """Remove bounding boxes that haven't been classified"""
        unclassifiedboxes = [bbox for bbox in self.boundingboxes
                             if not hasattr(bbox, 'classification') or bbox.classification is None]
        for bbox in unclassifiedboxes:
            if bbox.canvasid:
                self.imagecanvas.delete(bbox.canvasid)
            self.boundingboxes.remove(bbox)
        return len(unclassifiedboxes)

    def saveannotations(self, filename):
        """Save bounding box coordinates and classifications to a JSON file"""
        if not self.boundingboxes:
            print("No boxes to save")
            return
        basename = os.path.splitext(filename)[0]
        annotationfile = os.path.join(self.selectedfolder, f"{basename}.txt")
        try:
            classifiedboxes = [bbox for bbox in self.boundingboxes if
                               hasattr(bbox, 'classification') and bbox.classification is not None]
            if not classifiedboxes:
                print("No classified boxes to save")
                return

            annotationdata = {
                'imagefilename': filename,
                'imagepath': os.path.join(self.selectedfolder, filename),
                'imagesize': (self.originalimage.width if self.originalimage else 0,
                              self.originalimage.height if self.originalimage else 0),
                'annotations': []
            }

            for i, bbox in enumerate(classifiedboxes):
                origx1 = (bbox.x1 - self.imageoffsetx) / self.displayscale
                origy1 = (bbox.y1 - self.imageoffsety) / self.displayscale
                origx2 = (bbox.x2 - self.imageoffsetx) / self.displayscale
                origy2 = (bbox.y2 - self.imageoffsety) / self.displayscale
                width = abs(origx2 - origx1)
                height = abs(origy2 - origy1)
                centerx = (origx1 + origx2) / 2
                centery = (origy1 + origy2) / 2
                classificationkey = bbox.classification
                classificationname = bbox.get_classification_name() if hasattr(bbox,
                                                                               'get_classification_name') else 'Unclassified'

                annotation = {
                    'id': i + 1,
                    'classification': {'key': classificationkey, 'name': classificationname},
                    'bbox': {
                        'x1': round(origx1, 2), 'y1': round(origy1, 2),
                        'x2': round(origx2, 2), 'y2': round(origy2, 2),
                        'width': round(width, 2), 'height': round(height, 2),
                        'centerx': round(centerx, 2), 'centery': round(centery, 2)
                    }
                }
                annotationdata['annotations'].append(annotation)

            with open(annotationfile, 'w') as f:
                json.dump(annotationdata, f, indent=2)
            print(f"Saved {len(classifiedboxes)} classified annotations to {annotationfile}")

            unclassifiedcount = len(self.boundingboxes) - len(classifiedboxes)
            if unclassifiedcount > 0:
                print(f"Skipped {unclassifiedcount} unclassified boxes")
        except Exception as e:
            messagebox.showerror("Error", f"Could not save annotations: {str(e)}")

    def loadannotations(self, filename):
        """Load bounding box coordinates and classifications from JSON file"""
        # Clear existing boxes first
        self.boundingboxes.clear()

        basename = os.path.splitext(filename)[0]
        annotationfile = os.path.join(self.selectedfolder, f"{basename}.txt")
        if not os.path.exists(annotationfile):
            self.updateannotationlist()
            return
        try:
            with open(annotationfile, 'r') as f:
                content = f.read().strip()
            if not content:
                print(f"Empty annotation file: {annotationfile}")
                self.updateannotationlist()
                return
            try:
                annotationdata = json.loads(content)
            except json.JSONDecodeError as e:
                print(f"Invalid JSON in {annotationfile}: {e}")
                self.updateannotationlist()
                return

            for annotation in annotationdata.get('annotations', []):
                bboxdata = annotation['bbox']
                classificationdata = annotation['classification']
                origx1 = bboxdata['x1']
                origy1 = bboxdata['y1']
                origx2 = bboxdata['x2']
                origy2 = bboxdata['y2']

                canvasx1 = origx1 * self.displayscale + self.imageoffsetx
                canvasy1 = origy1 * self.displayscale + self.imageoffsety
                canvasx2 = origx2 * self.displayscale + self.imageoffsetx
                canvasy2 = origy2 * self.displayscale + self.imageoffsety

                classificationkey = classificationdata['key']
                bbox = BoundingBox(canvasx1, canvasy1, canvasx2, canvasy2)
                bbox.classification = classificationkey
                color = bbox.get_color() if hasattr(bbox, 'get_color') else '#0000FF'
                canvasid = self.imagecanvas.create_rectangle(canvasx1, canvasy1, canvasx2, canvasy2, outline=color,
                                                             width=2, tags=bbox)
                bbox.canvasid = canvasid
                self.boundingboxes.append(bbox)
            print(f"Loaded {len(annotationdata.get('annotations', []))} annotations")
            self.updateannotationlist()
        except Exception as e:
            print(f"Could not load annotations from {annotationfile}: {str(e)}")
            messagebox.showerror("Error", f"Could not load annotations: {str(e)}")
            self.updateannotationlist()

    def savecurrentannotations(self):
        """Save annotations for current image"""
        if self.currentindex < 0:
            return
        unclassifiedcount = self.cleanupunclassifiedboxes()
        if unclassifiedcount > 0:
            messagebox.showinfo("Info",
                                f"Removed {unclassifiedcount} unclassified boxes. Only classified boxes are saved.")
        currentfilename = self.filelistbox.get(self.currentindex)
        self.saveannotations(currentfilename)
        classifiedcount = len([bbox for bbox in self.boundingboxes if
                               hasattr(bbox, 'classification') and bbox.classification is not None])
        messagebox.showinfo("Success", f"Saved {classifiedcount} classified annotations!")
        self.updateannotationlist()


if __name__ == "__main__":
    app = ImageViewer()
    app.mainloop()
