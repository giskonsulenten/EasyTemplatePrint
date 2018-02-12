# -*- coding: utf-8 -*-
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    copyright            : (C) 2014-2015 by Sandro Mani / Sourcepole AG
#    email                : smani@sourcepole.ch
"""
/***************************************************************************
 EasyTemplatePrint 

                                 A QGIS plugin
 This plugin makes it easy to print using templates and text variables

 InstantPrintTool courtesy of the above smani@sourcepole.ch
 Adjusted and added functionality by:

                              -------------------
        begin                : 2018-01-08
        git sha              : $Format:%H$
        copyright            : (C) 2018 by Jesper Jøker Eg / GISkonsulenten
        email                : jesper@giskonsulenten.dk
 ***************************************************************************/
"""

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.core import *
from qgis.gui import *
import os
import math
import shapely
from shapely import affinity
from shapely.geometry import Point, LineString, Polygon

from EasyTemplatePrint_dialog import EasyTemplatePrintDialog

class InstantPrintTool(QgsMapTool):    
  
    def __init__(self, iface, populateCompositionFz=None):
        QgsMapTool.__init__(self, iface.mapCanvas())

        self.iface = iface
        self.rubberband = None
        self.oldrubberband = None
        self.pressPos = None
        self.populateCompositionFz = populateCompositionFz
        
        self.dialog = QDialog(self.iface.mainWindow())
        self.dialogui = EasyTemplatePrintDialog()
        self.dialogui.setupUi(self.dialog)
        self.exportButton = self.dialogui.buttonBox.addButton(self.tr("Export"), QDialogButtonBox.ActionRole)
        self.helpButton = self.dialogui.buttonBox.addButton(self.tr("Help"), QDialogButtonBox.HelpRole)
        self.helpButton.setEnabled(True)
        self.dialogui.comboBox_fileformat.addItem("PDF", self.tr("PDF Document (*.pdf);;"))
        self.dialogui.comboBox_fileformat.addItem("JPG", self.tr("JPG Image (*.jpg);;"))
        self.dialogui.comboBox_fileformat.addItem("BMP", self.tr("BMP Image (*.bmp);;"))
        self.dialogui.comboBox_fileformat.addItem("PNG", self.tr("PNG Image (*.png);;"))
        self.dialogui.spinBoxScale.valueChanged.connect(self.__changeScale)
        self.dialogui.spinBoxRotation.valueChanged.connect(self.__changeRotation)
        
        self.iface.composerAdded.connect(lambda view: self.__reloadComposers())
        self.iface.composerWillBeRemoved.connect(self.__reloadComposers)
        self.dialogui.comboBox_composers.currentIndexChanged.connect(self.__selectComposer)
        self.exportButton.clicked.connect(self.__export)
        self.helpButton.clicked.connect(self.__help)
        self.dialogui.buttonBox.button(QDialogButtonBox.Close).clicked.connect(lambda: self.setEnabled(False))
        self.setCursor(Qt.OpenHandCursor)
        
    def setEnabled(self, enabled):
        if enabled:
            self.dialog.setVisible(True)
            self.__reloadComposers()
            self.__selectComposer()
            self.iface.mapCanvas().setMapTool(self)
        else:
            self.dialog.setVisible(False)
            self.__cleanup()
            self.iface.mapCanvas().unsetMapTool(self)
            #QSettings().setValue("geometry", self.dialog.saveGeometry())

    def __changeRotation(self):
        if not self.mapitem:
            return
        self.mapitem.setMapRotation(self.dialogui.spinBoxRotation.value())
        self.__createRubberBand()
        
    def __changeScale(self):
        if not self.mapitem:
            return
        newscale = self.dialogui.spinBoxScale.value()
        extent = self.mapitem.extent()
        center = extent.center()
        newwidth = extent.width() / self.mapitem.scale() * newscale
        newheight = extent.height() / self.mapitem.scale() * newscale
        x1 = center.x() - 0.5 * newwidth
        y1 = center.y() - 0.5 * newheight
        x2 = center.x() + 0.5 * newwidth
        y2 = center.y() + 0.5 * newheight
        self.mapitem.setNewExtent(QgsRectangle(x1, y1, x2, y2))
        self.__createRubberBand()
        
    def __selectComposer(self):
        chk = ' []@%'
        labels = []    
        
        if not self.dialog.isVisible():
            return
        activeIndex = self.dialogui.comboBox_composers.currentIndex()
        if activeIndex < 0:
            return
        
        composerView = self.dialogui.comboBox_composers.itemData(activeIndex)
        try:
            maps = composerView.composition().composerMapItems()
        except:
            maps = []
            for item in composerView.composition().items():
                if isinstance(item, QgsComposerMap):
                    maps.append(item)
        
        if len(maps) != 1:
            QMessageBox.warning(self.iface.mainWindow(), self.tr("Invalid composer"), self.tr("The composer must have exactly one map item."))
            self.exportButton.setEnabled(False)
            self.dialogui.spinBoxScale.setEnabled(False)
            self.dialogui.spinBoxRotation.setEnabled(False)
            return
        
        self.dialogui.spinBoxScale.setEnabled(True)
        self.dialogui.spinBoxRotation.setEnabled(True)        
        self.exportButton.setEnabled(True)
        
        self.composerView = composerView
        self.mapitem = maps[0]
        self.dialogui.spinBoxScale.setValue(self.mapitem.scale())
        self.mapitem.setMapRotation(0)
        
        def containsAll(str,set):
            return 0 not in [c in str for c in set]
            
        stdVars = ['qgis_os_name','qgis_platform','qgis_release_name','qgis_version','qgis_version_no','user_account_name','user_full_name','project_filename','project_folder','project_title']
        for item in composerView.composition().items():
            if isinstance(item,QgsComposerLabel):
                if containsAll(item.text(),chk)!=0 and "\n" not in item.text():
                    if not any(item.text().strip('[]\@% ') in x  for x in stdVars):
                        labels.append(item.text().strip('[]\@% ').rstrip())
        # Clean dialogitems
        lineEditsList = [self.dialogui.lineEdit1,self.dialogui.lineEdit2,self.dialogui.lineEdit3,self.dialogui.lineEdit4,self.dialogui.lineEdit5]
        labelList =[self.dialogui.label_1,self.dialogui.label_2,self.dialogui.label_3,self.dialogui.label_4,self.dialogui.label_5]
        for l in lineEditsList:
            l.clear()
            l.setVisible(False)
        for l in labelList:
            l.clear()
            l.setVisible(False)
        count = len(labels) 
        if count==1:
            self.dialogui.lineEdit1.setText(labels[0])
            self.dialogui.lineEdit1.setVisible(True)
            self.dialogui.lineEdit2.setVisible(False)
            self.dialogui.lineEdit3.setVisible(False)
            self.dialogui.lineEdit4.setVisible(False)
            self.dialogui.lineEdit5.setVisible(False)
            self.dialogui.label_1.setText(labels[0] + ':')
            self.dialogui.label_1.setVisible(True)
            self.dialogui.label_2.setVisible(False)
            self.dialogui.label_3.setVisible(False)
            self.dialogui.label_4.setVisible(False)
            self.dialogui.label_5.setVisible(False)
            
        if count==2:
            self.dialogui.lineEdit1.setText(labels[0])
            self.dialogui.lineEdit2.setText(labels[1])
            self.dialogui.lineEdit1.setVisible(True)
            self.dialogui.lineEdit2.setVisible(True)
            self.dialogui.lineEdit3.setVisible(False)
            self.dialogui.lineEdit4.setVisible(False)
            self.dialogui.lineEdit5.setVisible(False)
            self.dialogui.label_1.setText(labels[0] + ':')
            self.dialogui.label_2.setText(labels[1] + ':')
            self.dialogui.label_1.setVisible(True)
            self.dialogui.label_2.setVisible(True)
            self.dialogui.label_3.setVisible(False)
            self.dialogui.label_4.setVisible(False)
            self.dialogui.label_5.setVisible(False)
        if count==3:            
            self.dialogui.lineEdit1.setText(labels[0])
            self.dialogui.lineEdit2.setText(labels[1])
            self.dialogui.lineEdit3.setText(labels[2])
            self.dialogui.lineEdit1.setVisible(True)
            self.dialogui.lineEdit2.setVisible(True)
            self.dialogui.lineEdit3.setVisible(True)
            self.dialogui.lineEdit4.setVisible(False)
            self.dialogui.lineEdit5.setVisible(False)
            self.dialogui.label_1.setText(labels[0] + ':')
            self.dialogui.label_2.setText(labels[1] + ':')
            self.dialogui.label_3.setText(labels[2] + ':')
            self.dialogui.label_1.setVisible(True)
            self.dialogui.label_2.setVisible(True)
            self.dialogui.label_3.setVisible(True)
            self.dialogui.label_4.setVisible(False)
            self.dialogui.label_5.setVisible(False)
        if count==4:
            self.dialogui.lineEdit1.setText(labels[0])
            self.dialogui.lineEdit2.setText(labels[1])
            self.dialogui.lineEdit3.setText(labels[2])
            self.dialogui.lineEdit4.setText(labels[3])
            self.dialogui.lineEdit1.setVisible(True)
            self.dialogui.lineEdit2.setVisible(True)
            self.dialogui.lineEdit3.setVisible(True)
            self.dialogui.lineEdit4.setVisible(True)
            self.dialogui.lineEdit5.setVisible(False)
            self.dialogui.label_1.setText(labels[0] + ':')
            self.dialogui.label_2.setText(labels[1] + ':')
            self.dialogui.label_3.setText(labels[2] + ':')
            self.dialogui.label_4.setText(labels[3] + ':')
            self.dialogui.label_1.setVisible(True)
            self.dialogui.label_2.setVisible(True)
            self.dialogui.label_3.setVisible(True)
            self.dialogui.label_4.setVisible(True)
            self.dialogui.label_5.setVisible(False)
        if count==5:
            self.dialogui.lineEdit1.setText(labels[0])
            self.dialogui.lineEdit2.setText(labels[1])
            self.dialogui.lineEdit3.setText(labels[2])
            self.dialogui.lineEdit4.setText(labels[3])
            self.dialogui.lineEdit5.setText(labels[4])
            self.dialogui.lineEdit1.setVisible(True)
            self.dialogui.lineEdit2.setVisible(True)
            self.dialogui.lineEdit3.setVisible(True)
            self.dialogui.lineEdit4.setVisible(True)
            self.dialogui.lineEdit5.setVisible(True)
            self.dialogui.label_1.setText(labels[0] + ':')
            self.dialogui.label_2.setText(labels[1] + ':')
            self.dialogui.label_3.setText(labels[2] + ':')
            self.dialogui.label_4.setText(labels[3] + ':')
            self.dialogui.label_5.setText(labels[4] + ':')
            self.dialogui.label_1.setVisible(True)
            self.dialogui.label_2.setVisible(True)
            self.dialogui.label_3.setVisible(True)
            self.dialogui.label_4.setVisible(True)
            self.dialogui.label_5.setVisible(True)
        
        self.__createRubberBand()
  
    def __createRubberBand(self):
        self.__cleanup()
        extent = self.mapitem.extent()
        center = self.iface.mapCanvas().extent().center()
        self.corner = QPointF(center.x() - 0.5 * extent.width(), center.y() - 0.5 * extent.height())
        self.rect = QRectF(self.corner.x(), self.corner.y(), extent.width(), extent.height())
        self.mapitem.setNewExtent(QgsRectangle(self.rect))

        self.__createRubberbandAsGeometry()
               
        self.pressPos = None

    def __cleanup(self):
        if self.rubberband:
            self.iface.mapCanvas().scene().removeItem(self.rubberband)
        if self.oldrubberband:
            self.iface.mapCanvas().scene().removeItem(self.oldrubberband)
        self.rubberband = None
        self.oldrubberband = None
        self.pressPos = None

    def canvasPressEvent(self, e):
        if not self.rubberband:
            return
        r = self.__canvasRect(self.rect)
        posMap = QgsPoint(self.toMapCoordinates(e.pos()).x(), self.toMapCoordinates(e.pos()).y())
        pos = QPointF(posMap.x(), posMap.y())	
        
        if e.button() == Qt.LeftButton and self.__canvasRect(self.rect).contains(pos):
            self.pressPos = (pos.x(), pos.y())
            self.iface.mapCanvas().setCursor(Qt.ClosedHandCursor)

    def canvasMoveEvent(self, e):
        if not self.pressPos:
            return
        mapPoint = self.toMapCoordinates(e.pos())
        x = self.corner.x() + (mapPoint.x() - self.pressPos[0]) #* mup
        y = self.corner.y() + (mapPoint.y() - self.pressPos[1]) #* mup

        self.rect = QRectF(
            x,
            y,
            self.rect.width(),
            self.rect.height()
        )
        self.__createRubberbandAsGeometry()
        
    def __createRubberbandAsGeometry(self):
        
        lTopx = self.__canvasRect(self.rect).x()
        lTopy = self.__canvasRect(self.rect).y() + self.__canvasRect(self.rect).height()
        rTopx = self.__canvasRect(self.rect).x() + self.__canvasRect(self.rect).width()
        rTopy = self.__canvasRect(self.rect).y() + self.__canvasRect(self.rect).height()
        rBotx = self.__canvasRect(self.rect).x() + self.__canvasRect(self.rect).width()
        rBoty = self.__canvasRect(self.rect).y()
        lBotx = self.__canvasRect(self.rect).x()
        lBoty = self.__canvasRect(self.rect).y()
        polygon = Polygon(((lBotx, lBoty), (lTopx, lTopy), (rTopx, rTopy), (rBotx, rBoty)))
        
        if self.rubberband:
            self.iface.mapCanvas().scene().removeItem(self.rubberband)
        
        if self.dialogui.spinBoxRotation.value()>0:
            rotatedPolygon = shapely.affinity.rotate(polygon, self.dialogui.spinBoxRotation.value(), origin='centroid', use_radians=False)
            x,y = rotatedPolygon.exterior.coords.xy
            points = [[QgsPoint(x[0],y[0]), QgsPoint(x[1], y[1]), QgsPoint(x[2], y[2]), QgsPoint(x[3], y[3])]]
            self.rubberband = QgsRubberBand(self.iface.mapCanvas(), QGis.Polygon)
            self.rubberband.setToGeometry(QgsGeometry.fromPolygon(points), None)
            self.rubberband.setColor(QColor(127, 127, 255, 127))
        
        if self.dialogui.spinBoxRotation.value()==0:
            points = [[QgsPoint(lBotx, lBoty), QgsPoint(lTopx, lTopy), QgsPoint(rTopx, rTopy), QgsPoint(rBotx, rBoty)]]
            self.rubberband = QgsRubberBand(self.iface.mapCanvas(), QGis.Polygon)
            self.rubberband.setToGeometry(QgsGeometry.fromPolygon(points), None)
            self.rubberband.setColor(QColor(127, 127, 255, 127))
               
    def canvasReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.pressPos:
            self.corner = QPointF(self.rect.x(), self.rect.y())
            self.pressPos = None
            self.iface.mapCanvas().setCursor(Qt.OpenHandCursor)
            self.iface.mapCanvas().scene().removeItem(self.oldrubberband)
            self.oldrect = None
            self.oldrubberband = None
            #if self.dialogui.spinBoxRotation.value()==0:
            self.mapitem.setNewExtent(QgsRectangle(self.rect))
                            
    def __canvasRect(self, rect):
        # Now in map coordinates
        p1 = QgsPoint(rect.left(), rect.top())
        p2 = QgsPoint(rect.right(), rect.bottom())
        text = "__canvasRect " + str(p1.x()) + ', ' + str(p1.y()) + ', ' + str(p2.x() - p1.x()) + ', ' + str(p2.y() - p1.y())
        return QRectF(p1.x(), p1.y(), p2.x() - p1.x(), p2.y() - p1.y())
                
    def __export(self):
        labelName = [self.dialogui.label_1.text().strip(':'),self.dialogui.label_2.text().strip(':'),self.dialogui.label_3.text().strip(':'),self.dialogui.label_4.text().strip(':'),self.dialogui.label_5.text().strip(':')] 
        labelText = [self.dialogui.lineEdit1.text(),self.dialogui.lineEdit2.text(),self.dialogui.lineEdit3.text(),self.dialogui.lineEdit4.text(),self.dialogui.lineEdit5.text()]  
        idx = 0
        for l in labelName:
            QgsExpressionContextUtils.setProjectVariable(l,labelText[idx])
            idx = idx + 1
        settings = QSettings()
        format = self.dialogui.comboBox_fileformat.itemData(self.dialogui.comboBox_fileformat.currentIndex())
        filename = QFileDialog.getSaveFileName(
            self.iface.mainWindow(),
            self.tr("Print Composition"),
            settings.value("/instantprint/lastfile", ""),
            format
        )
        if not filename:
            return
        # Ensure output filename has correct extension
        filename = os.path.splitext(filename)[0] + "." + self.dialogui.comboBox_fileformat.currentText().lower()
        settings.setValue("/instantprint/lastfile", filename)
        if self.populateCompositionFz:
            self.populateCompositionFz(self.composerView.composition())
        success = False
        if filename[-3:].lower() == u"pdf":
            success = self.composerView.composition().exportAsPDF(filename)
        else:
            image = self.composerView.composition().printPageAsRaster(self.composerView.composition().itemPageNumber(self.mapitem))
            if not image.isNull():
                success = image.save(filename)
        if not success:
            QMessageBox.warning(self.iface.mainWindow(), self.tr("Print Failed"), self.tr("Failed to print the composition."))
        else:
            # Message when print is ready
            QMessageBox.information(None,self.tr("Information"), self.tr("Finished export to file: \n\n" + filename))

    def __reloadComposers(self, removed=None):
        if not self.dialog.isVisible():
            return
        self.dialogui.comboBox_composers.blockSignals(True)
        prev = None
        if self.dialogui.comboBox_composers.currentIndex() >= 0:
            prev = self.dialogui.comboBox_composers.currentText()
        self.dialogui.comboBox_composers.clear()
        self.dialogui.comboBox_composers.setInsertPolicy(6)
        active = 0
        for composer in self.iface.activeComposers():
            if composer != removed and composer.composerWindow():
                cur = composer.composerWindow().windowTitle()
                self.dialogui.comboBox_composers.addItem(cur, composer)
                if prev == cur:
                    active = self.dialogui.comboBox_composers.count() - 1
        self.dialogui.comboBox_composers.setCurrentIndex(-1)  # Ensure setCurrentIndex below actually changes an index
        self.dialogui.comboBox_composers.setCurrentIndex(-1)  # Ensure setCurrentIndex below actually changes an index
        self.dialogui.comboBox_composers.blockSignals(False)
        if self.dialogui.comboBox_composers.count() > 0:
            self.dialogui.comboBox_composers.model().sort(0)
            self.dialogui.comboBox_composers.setCurrentIndex(active)
            self.dialogui.spinBoxScale.setEnabled(True)
            self.exportButton.setEnabled(True)
        else:
            self.exportButton.setEnabled(False)
            self.dialogui.spinBoxScale.setEnabled(False)

    def __help(self):
        manualPath = os.path.join(os.path.dirname(__file__), "help", "documentation.pdf")
        QDesktopServices.openUrl(QUrl.fromLocalFile(manualPath))
