import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk, ImageDraw
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
        'N': 'NVD',
        'V': 'Vitreous hemorrhage',
        'X': 'NVE',
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
        margin = 5
        return (self.x1 - margin) <= x <= (self.x2 + margin) and (self.y1 - margin) <= y <= (self.y2 + margin)

    def get_color(self):
        """Get color based on classification"""
        if self.classification:
            colors = {'M': 'yellow', 'H': 'red', 'D': 'blue', 'A': 'green', 'C': 'orange', 'F': 'cyan',
                      'E': 'magenta', 'L': 'purple', 'N': 'pink', 'V': 'brown', 'O': 'gray', 'X':'black'}
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
        self.preprocessedfolder = None  # NEW: Folder for preprocessed images
        self.currentimage = None
        self.currentindex = -1
        self.originalimage = None
        self.preprocessedimage = None  # NEW: Store preprocessed image
        self.displayscale = 1.0
        self.imageoffsetx = 0
        self.imageoffsety = 0

        # Magnifier settings - will be dynamically updated
        self.magnifierzoom = 3.0
        self.magnifiersize = 300  # Initial size, will be updated dynamically
        self.magnifiedimage = None
        self.rightpane = None  # Store reference to right pane

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

        # Context menu for bounding boxes
        self.contextmenu = None

        self.imageextensions = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ppm', '.pgm', '.pbm')
        self.createtopnavbar()
        self.createcontainerframe()
        self.createcontextmenu()
        self.bindcanvasevents()
        self.bindkeyboardevents()

        # Bind resize event to update magnifier size
        self.bind('<Configure>', self.onwindowresize)

    def createtopnavbar(self):
        buttonframe = tk.Frame(self, bg='white')
        buttonframe.pack(side=tk.TOP, fill='x', anchor='w', pady=5)

        btnselect = tk.Button(buttonframe, text="Select Original Folder", command=self.selectfolder)
        btnpreprocessed = tk.Button(buttonframe, text="Select Preprocessed Folder",
                                    command=self.selectpreprocessedfolder, bg='#ffe6cc')  # NEW
        btnright = tk.Button(buttonframe, text="Next >", command=self.nextimage)
        btnleft = tk.Button(buttonframe, text="< Previous", command=self.previousimage)

        btnclearboxes = tk.Button(buttonframe, text="Clear All Boxes", command=self.clearallboxes, bg='#ffcccc')
        btndeleteselected = tk.Button(buttonframe, text="Delete Selected", command=self.deleteselectedbox, bg='#ffdddd')
        btnsave = tk.Button(buttonframe, text="Save Annotations", command=self.savecurrentannotations, bg='#ccffcc')

        btnzoomin = tk.Button(buttonframe, text="Zoom+", command=self.increasemagnifierzoom, bg='#e6f2ff')
        btnzoomout = tk.Button(buttonframe, text="Zoom-", command=self.decreasemagnifierzoom, bg='#e6f2ff')

        # Status label for annotation count
        self.statuslabel = tk.Label(buttonframe, text="Annotations: 0", font=('Arial', 10), bg='white')

        btnsave.pack(side=tk.LEFT, padx=5, pady=5)
        btnselect.pack(side=tk.LEFT, padx=5, pady=5)
        btnpreprocessed.pack(side=tk.LEFT, padx=5, pady=5)  # NEW
        btnclearboxes.pack(side=tk.LEFT, padx=5, pady=5)
        btndeleteselected.pack(side=tk.LEFT, padx=5, pady=5)
        btnzoomin.pack(side=tk.LEFT, padx=3, pady=5)
        btnzoomout.pack(side=tk.LEFT, padx=3, pady=5)
        self.statuslabel.pack(side=tk.LEFT, padx=10, pady=5)
        btnright.pack(side=tk.RIGHT, padx=10, pady=5)
        btnleft.pack(side=tk.RIGHT, padx=10, pady=5)

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

        # Left pane: 10% file list
        leftpane = tk.Frame(container, bg='white')
        leftpane.place(relx=0, rely=0, relwidth=0.10, relheight=1)
        tk.Label(leftpane, text="Files", bg='white', font=('Arial', 10, 'bold')).pack(padx=5, pady=(10, 5))
        self.filelistbox = tk.Listbox(leftpane, bg='white', font=('Arial', 9))
        self.filelistbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.filelistbox.bind('<<ListboxSelect>>', self.onfileselect)

        # Middle pane: 70% image display
        middlepane = tk.Frame(container, bg='white')
        middlepane.place(relx=0.10, rely=0, relwidth=0.70, relheight=1)
        self.filenamelabel = tk.Label(middlepane, text="Select an image to view", font=('Arial', 12), bg='white')
        self.filenamelabel.pack(padx=10, pady=10)

        self.imagecanvas = tk.Canvas(middlepane, bg='white', highlightthickness=0)
        self.imagecanvas.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Right pane: 20% magnifier panel
        self.rightpane = tk.Frame(container, bg='lightgray', relief=tk.RAISED, bd=2)
        self.rightpane.place(relx=0.80, rely=0, relwidth=0.20, relheight=1)

        # NEW: Magnifier title with source indicator
        self.magnifiertitle = tk.Label(self.rightpane, text="Magnifier (Original)", font=('Arial', 12, 'bold'),
                                       bg='lightgray')
        self.magnifiertitle.pack(pady=(10, 5))

        # Magnifier canvas - will be resized dynamically
        self.magnifiercanvas = tk.Canvas(self.rightpane, bg='white', width=self.magnifiersize,
                                         height=self.magnifiersize)
        self.magnifiercanvas.pack(pady=5, padx=10)

        self.magnifierlabel = tk.Label(self.rightpane, text="Move cursor over image", font=('Arial', 10),
                                       bg='lightgray')
        self.magnifierlabel.pack(pady=5)

        self.zoomfactorlabel = tk.Label(self.rightpane, text=f"Zoom: {self.magnifierzoom}x", font=('Arial', 10),
                                        bg='lightgray')
        self.zoomfactorlabel.pack(pady=5)

        # NEW: Preprocessed folder status label
        self.preprocessedlabel = tk.Label(self.rightpane, text="Preprocessed: Not set", font=('Arial', 9),
                                          bg='lightgray', fg='gray')
        self.preprocessedlabel.pack(pady=5)

        # Annotation list in right pane
        tk.Label(self.rightpane, text="Annotations", font=('Arial', 12, 'bold'), bg='lightgray').pack(pady=(15, 5))
        self.annotationlistbox = tk.Listbox(self.rightpane, bg='white', height=10, font=('Arial', 10))
        self.annotationlistbox.pack(pady=5, padx=10, fill=tk.BOTH, expand=True)
        self.annotationlistbox.bind('<Double-Button-1>', self.selectannotationfromlist)
        self.annotationlistbox.bind('<Button-3>', self.showcontextmenuforlist)

    def onwindowresize(self, event):
        """Handle window resize to update magnifier size dynamically"""
        if self.rightpane and event.widget == self:
            # Calculate new magnifier size based on right pane width
            self.after(100, self.updatemagnifiersize)

    def updatemagnifiersize(self):
        """Update magnifier canvas size based on right pane width"""
        try:
            panewidth = self.rightpane.winfo_width()
            # Make magnifier square and fit within the pane with some padding
            newsize = max(150, panewidth - 40)  # Minimum 150, with 20px padding on each side

            if newsize != self.magnifiersize:
                self.magnifiersize = newsize
                self.magnifiercanvas.config(width=self.magnifiersize, height=self.magnifiersize)
        except:
            pass

    def bindcanvasevents(self):
        """Bind mouse events for bounding box functionality"""
        self.imagecanvas.bind('<Button-1>', self.oncanvasclick)
        self.imagecanvas.bind('<B1-Motion>', self.oncanvasdrag)
        self.imagecanvas.bind('<ButtonRelease-1>', self.oncanvasrelease)
        self.imagecanvas.bind('<Button-3>', self.onrightclick)
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
        self.bind('x', lambda e: self.classifybox('X'))
        self.bind('X', lambda e: self.classifybox('X'))
        self.focus_set()

    def onmousemove(self, event):
        """Handle mouse movement to update magnifier with preprocessed image and bounding boxes"""
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
            # NEW: Use preprocessed image if available, otherwise use original
            magnifiersource = self.preprocessedimage if self.preprocessedimage else self.originalimage
            sourcewidth, sourceheight = magnifiersource.size

            # Calculate scale factor if preprocessed image has different dimensions
            scalex = sourcewidth / imgwidth
            scaley = sourceheight / imgheight

            # Adjust coordinates for preprocessed image
            adjorigx = origx * scalex
            adjorigy = origy * scaley

            cropsize = self.magnifiersize / self.magnifierzoom
            # Adjust crop size for preprocessed image scale
            adjcropsize = cropsize * scalex  # Assuming uniform scaling

            left = adjorigx - adjcropsize / 2
            top = adjorigy - adjcropsize / 2
            right = adjorigx + adjcropsize / 2
            bottom = adjorigy + adjcropsize / 2

            # Calculate the actual crop boundaries (clamped to image)
            cropleft = max(0, int(left))
            croptop = max(0, int(top))
            cropright = min(sourcewidth, int(right))
            cropbottom = min(sourceheight, int(bottom))

            cropped = magnifiersource.crop((cropleft, croptop, cropright, cropbottom))
            magnified = cropped.resize((self.magnifiersize, self.magnifiersize), Image.Resampling.NEAREST)

            # Convert to drawable image to add bounding boxes
            magnifieddraw = magnified.copy()
            draw = ImageDraw.Draw(magnifieddraw)

            # Draw bounding boxes that are visible in the magnified area
            # Use original image coordinates for bounding boxes
            origleft = origx - cropsize / 2
            origtop = origy - cropsize / 2
            origright = origx + cropsize / 2
            origbottom = origy + cropsize / 2

            for bbox in self.boundingboxes:
                # Convert canvas coordinates to original image coordinates
                bboxorigx1 = (bbox.x1 - self.imageoffsetx) / self.displayscale
                bboxorigy1 = (bbox.y1 - self.imageoffsety) / self.displayscale
                bboxorigx2 = (bbox.x2 - self.imageoffsetx) / self.displayscale
                bboxorigy2 = (bbox.y2 - self.imageoffsety) / self.displayscale

                # Check if bbox intersects with the visible magnifier area (using original coords)
                if (bboxorigx2 >= origleft and bboxorigx1 <= origright and
                        bboxorigy2 >= origtop and bboxorigy1 <= origbottom):

                    # Convert to magnifier coordinates
                    magx1 = (bboxorigx1 - origleft) * self.magnifierzoom
                    magy1 = (bboxorigy1 - origtop) * self.magnifierzoom
                    magx2 = (bboxorigx2 - origleft) * self.magnifierzoom
                    magy2 = (bboxorigy2 - origtop) * self.magnifierzoom

                    # Clamp to magnifier bounds
                    magx1 = max(0, min(self.magnifiersize, magx1))
                    magy1 = max(0, min(self.magnifiersize, magy1))
                    magx2 = max(0, min(self.magnifiersize, magx2))
                    magy2 = max(0, min(self.magnifiersize, magy2))

                    # Get color for the bounding box
                    color = bbox.get_color() if bbox.classification else 'blue'
                    if bbox.selected:
                        color = 'green'

                    # Draw the rectangle with thicker line for visibility
                    linewidth = 3 if bbox.selected else 2
                    draw.rectangle([magx1, magy1, magx2, magy2], outline=color, width=linewidth)

                    # Draw classification label if classified
                    if bbox.classification:
                        labeltext = bbox.classification
                        # Draw label background
                        textbbox = draw.textbbox((magx1, magy1 - 15), labeltext)
                        if magy1 > 15:  # Label above box
                            draw.rectangle([textbbox[0] - 2, textbbox[1] - 2, textbbox[2] + 2, textbbox[3] + 2],
                                           fill=color)
                            draw.text((magx1, magy1 - 15), labeltext, fill='black')
                        else:  # Label inside box
                            draw.rectangle([textbbox[0] - 2, magy1 + 2, textbbox[2] + 2, magy1 + 17], fill=color)
                            draw.text((magx1, magy1 + 2), labeltext, fill='black')

            self.magnifiedimage = ImageTk.PhotoImage(magnifieddraw)

            self.magnifiercanvas.delete('all')
            self.magnifiercanvas.create_image(0, 0, anchor=tk.NW, image=self.magnifiedimage)

            # Draw crosshair
            center = self.magnifiersize // 2
            self.magnifiercanvas.create_line(center - 15, center, center + 15, center, fill='red', width=2)
            self.magnifiercanvas.create_line(center, center - 15, center, center + 15, fill='red', width=2)

            self.magnifierlabel.config(text=f"Position: ({int(origx)}, {int(origy)})")
        except Exception as e:
            print(f"Magnifier error: {e}")

    def increasemagnifierzoom(self):
        """Increase magnifier zoom factor"""
        self.magnifierzoom = min(10.0, self.magnifierzoom + 0.5)
        self.zoomfactorlabel.config(text=f"Zoom: {self.magnifierzoom}x")

    def decreasemagnifierzoom(self):
        """Decrease magnifier zoom factor"""
        self.magnifierzoom = max(1.0, self.magnifierzoom - 0.5)
        self.zoomfactorlabel.config(text=f"Zoom: {self.magnifierzoom}x")

    def selectfolder(self):
        """Select folder containing original images"""
        folderselected = filedialog.askdirectory(title="Select Original Images Folder")
        if folderselected:
            self.selectedfolder = folderselected
            self.displayfilesinfolder(folderselected)
        else:
            messagebox.showinfo("No Selection", "No folder selected!")

    def selectpreprocessedfolder(self):
        """NEW: Select folder containing preprocessed images"""
        folderselected = filedialog.askdirectory(title="Select Preprocessed Images Folder")
        if folderselected:
            self.preprocessedfolder = folderselected
            foldername = os.path.basename(folderselected)
            self.preprocessedlabel.config(text=f"Preprocessed: {foldername}", fg='green')
            self.magnifiertitle.config(text="Magnifier (Preprocessed)")

            # Reload current image to update magnifier
            if self.currentindex >= 0:
                filename = self.filelistbox.get(self.currentindex)
                self.loadpreprocessedimage(filename)

            messagebox.showinfo("Success", f"Preprocessed folder set:\n{folderselected}")
        else:
            messagebox.showinfo("No Selection", "No folder selected!")

    def loadpreprocessedimage(self, filename):
        """NEW: Load the corresponding preprocessed image"""
        if not self.preprocessedfolder:
            self.preprocessedimage = None
            return

        # Try to find matching file in preprocessed folder
        basename = os.path.splitext(filename)[0]

        # Try different extensions
        for ext in self.imageextensions:
            preprocessedpath = os.path.join(self.preprocessedfolder, basename + ext)
            if os.path.exists(preprocessedpath):
                try:
                    self.preprocessedimage = Image.open(preprocessedpath)
                    print(f"Loaded preprocessed image: {preprocessedpath}")
                    return
                except Exception as e:
                    print(f"Error loading preprocessed image: {e}")

        # Also try exact filename match
        preprocessedpath = os.path.join(self.preprocessedfolder, filename)
        if os.path.exists(preprocessedpath):
            try:
                self.preprocessedimage = Image.open(preprocessedpath)
                print(f"Loaded preprocessed image: {preprocessedpath}")
                return
            except Exception as e:
                print(f"Error loading preprocessed image: {e}")

        # No matching preprocessed image found
        self.preprocessedimage = None
        print(f"No preprocessed image found for: {filename}")

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

            # NEW: Load corresponding preprocessed image
            self.loadpreprocessedimage(filename)

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
            # FIXED: Remove the 1.0 constraint to allow images to scale down to fit
            self.displayscale = min(scalew, scaleh)
            newwidth = int(imgwidth * self.displayscale)
            newheight = int(imgheight * self.displayscale)
            self.imageoffsetx = (canvaswidth - newwidth) // 2
            self.imageoffsety = (canvasheight - newheight) // 2
            imgresized = self.originalimage.resize((newwidth, newheight), Image.Resampling.LANCZOS)
            self.currentimage = ImageTk.PhotoImage(imgresized)
            self.imagecanvas.create_image(self.imageoffsetx, self.imageoffsety, anchor=tk.NW, image=self.currentimage)
            self.loadannotations(filename)

            # NEW: Update magnifier title based on preprocessed image availability
            if self.preprocessedimage:
                self.magnifiertitle.config(text="Magnifier (Preprocessed)")
            else:
                self.magnifiertitle.config(text="Magnifier (Original)")

        except Exception as e:
            messagebox.showerror("Error", f"Could not load image: {str(e)}")

    def oncanvasclick(self, event):
        """Handle canvas click - start drawing bounding box or select existing"""
        clickedbox = self.findboxatpoint(event.x, event.y)
        if clickedbox:
            self.deselectallboxes()
            self.selectedbox = clickedbox
            clickedbox.selected = True
            self.imagecanvas.itemconfig(clickedbox.canvasid, outline='green', width=3)
            self.updateannotationlist()
            return

        self.deselectallboxes()
        self.startx = event.x
        self.starty = event.y
        self.drawingbox = True

    def findboxatpoint(self, x, y):
        """Find bounding box at given point"""
        for bbox in reversed(self.boundingboxes):
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

            try:
                self.contextmenu.tk_popup(event.x_root, event.y_root, 0)
            finally:
                self.contextmenu.grab_release()

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

    def reclassifybox(self):
        """Reclassify the selected bounding box"""
        if self.selectedbox:
            self.pendingclassification = self.selectedbox
            self.classificationmode = True
            self.showclassificationinstruction()

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
            self.imagecanvas.delete(self.selectedbox.canvasid)
            self.boundingboxes.remove(self.selectedbox)
            self.selectedbox = None
            self.updateannotationlist()
            self.updatestatusbar()
            print("Deleted selected annotation")

    def updateannotationlist(self):
        """Update the annotation listbox"""
        self.annotationlistbox.delete(0, tk.END)
        for i, bbox in enumerate(self.boundingboxes):
            classname = bbox.get_classification_name() if bbox.classification else "Unclassified"
            displaytext = f"{i + 1}. {classname}"
            if bbox.selected:
                displaytext += " *"
            self.annotationlistbox.insert(tk.END, displaytext)

            color = bbox.get_color() if bbox.classification else 'white'
            self.annotationlistbox.itemconfig(i, {'fg': color})
            if bbox.selected:
                self.annotationlistbox.itemconfig(i, {'bg': '#404040'})
                self.annotationlistbox.selection_set(i)
            else:
                self.annotationlistbox.itemconfig(i, {'bg': 'white'})
        self.updatestatusbar()

    def updatestatusbar(self):
        """Update status label with annotation count"""
        classified = len([b for b in self.boundingboxes if b.classification])
        total = len(self.boundingboxes)
        self.statuslabel.config(text=f"Annotations: {classified}/{total} classified")

    def showclassificationinstruction(self):
        """Show classification instruction to user"""
        instructiontext = "Classify: M(Macula), H(Hemorrhages), D(Disc), A(Microaneurysms), C(Cotton Wool Spots), F(Fovea), E(Hard Exudates), L(Laser marks), N(NVD), V(Vitreous hemorrhage),X(NVE), O(Other)"

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