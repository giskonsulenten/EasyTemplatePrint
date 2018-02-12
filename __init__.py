# -*- coding: utf-8 -*-
"""
/***************************************************************************
 EasyTemplatePrint
                                 A QGIS plugin
 This plugin makes it easy to print using templates and text variables
                             -------------------
        begin                : 2018-01-08
        copyright            : (C) 2018 by Jesper Jøker Eg / GISkonsulenten
        email                : jesper@giskonsulenten.dk
        git sha              : $Format:%H$
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
 This script initializes the plugin, making it known to QGIS.
"""


# noinspection PyPep8Naming
def classFactory(iface):  # pylint: disable=invalid-name
    """Load EasyTemplatePrint class from file EasyTemplatePrint.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    #
    from .EasyTemplatePrint import EasyTemplatePrint
    return EasyTemplatePrint(iface)
