#!/usr/bin/python
# -*- coding: utf-8 -*-

#   Copyright (C) 2010 Daniel Fett
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#   Author: Daniel Fett agtl@danielfett.de
#   Jabber: fett.daniel@jaber.ccc.de
#   Bugtracker and GIT Repository: http://github.com/webhamster/advancedcaching
#

import logging
logger = logging.getLogger('qtgui')

from PySide import QtGui
from PySide import QtDeclarative
from PySide import QtOpenGL
from PySide import QtCore
import os
import sys
import geo
geo.DEGREES = geo.DEGREES.decode('utf-8')
import re
import geocaching
import gpsreader
from os import path
from gui import Gui
from astral import Astral

d = lambda x: x#.decode('utf-8', 'replace')

class Controller(QtCore.QObject):

    changed = QtCore.Signal()
    progressChanged = QtCore.Signal()
    marksChanged = QtCore.Signal()
    
    def __init__(self, view, core):
        QtCore.QObject.__init__(self)
        self.view = view
        self.core = core
        self.current_cache = None
        self.core.connect('progress', self._show_progress)
        self.core.connect('hide-progress', self._hide_progress)
        self.core.connect('cache-changed', self._cache_changed)
        self.core.connect('error', self._show_message)
        self.core.connect('map-marks-changed', self._map_marks_changed)
        self.core.connect('settings-changed', self._settings_changed)
        self.callback_gps = None
        self.c = None
        self._progress_visible = False
        self._progress = 0
        self._progress_message = ""


    # Handle gobject signal from Core
    def _map_marks_changed(self, caller):
        self.marksChanged.emit()

    # Handle gobject signal from Core
    def _show_message(self, caller, message):
        self.view.rootObject().showMessage(str(message))

    # Handle gobject signal from Core
    def _cache_changed(self, caller, cache):
        if self.current_cache != None and self.current_cache.name == cache.name:
            self.current_cache.update(cache)

    # Handle gobject signal from Core
    def _hide_progress(self, caller):
        self._progress_visible = False
        logger.debug("Hide progress")
        self.progressChanged.emit()

    # Handle gobject signal from Core
    def _show_progress(self, caller, progress, message):
        #logger.debug("Show Progress")
        #self.view.rootObject().showProgress(progress, str(message))
        #logger.debug("Showed Progress")
        self._progress_visible = True
        self._progress = float(progress)
        self._progress_message = str(message)
        self.progressChanged.emit()

    # Handle gobject signal from Core
    def _settings_changed(self, caller, settings, source):
        if source == self or type(source) == SettingsWrapper:
            return
        logger.debug("Got settings from %s, len() = %d, source = %s" % (caller, len(settings), source))

        if 'last_selected_geocache' in settings:
            c = self.core.pointprovider.get_by_name(settings['last_selected_geocache'])
            if c != None:
                self.geocacheSelected(GeocacheWrapper(c, self.core))
        if 'last_target_lat' in settings and 'last_target_lon' in settings:
            self.setTarget(settings['last_target_lat'], settings['last_target_lon'])
        #if 'last_target_lat' in settings:
        #    self.setTarget(settings['last_target_lat'], settings['last_target_lon'])


    @QtCore.Slot(QtCore.QObject)
    def geocacheDownloadDetailsClicked(self, wrapper):
        self.core.on_download_cache(wrapper._geocache)

    @QtCore.Slot(QtCore.QObject)
    def geocacheSelected(self, wrapper):
        self.current_cache = wrapper
        self.view.rootObject().setCurrentGeocache(wrapper)
        #self.updateSetting('last_selected_geocache', wrapper._name())

    @QtCore.Slot(QtCore.QObject, float, float, float, float)
    def mapViewChanged(self, map, lat_start, lon_start, lat_end, lon_end):
        #logger.debug("Map view changed to %r-%r, %r-%r." % (lat_start, lon_start, lat_end, lon_end))
        logger.debug("0. map view changed")
        if self.view.rootObject() != None:
            self.view.rootObject().setGeocacheList(map, GeocacheListModel(self.core, lat_start, lon_start, lat_end, lon_end))
            logger.debug("5. data set")

    @QtCore.Slot(float, float, float, float)
    def updateGeocaches(self, lat_start, lon_start, lat_end, lon_end):
        self.core.on_download([geo.Coordinate(lat_start, lon_start), geo.Coordinate(lat_end, lon_end)])

    @QtCore.Slot(float, float, float, float)
    def downloadGeocaches(self, lat_start, lon_start, lat_end, lon_end):
        self.core.on_download_descriptions([geo.Coordinate(lat_start, lon_start), geo.Coordinate(lat_end, lon_end)])

    @QtCore.Slot(float, float)
    def setTarget(self, lat, lon):
        #self.settings['last_target_lat'], self.settings['last_target_lon'] = lat, lon
        logger.debug("Setting target to %f, %f" % (lat, lon))
        self.core.set_target(geo.Coordinate(lat, lon))

    @QtCore.Slot(QtCore.QObject)
    def setAsTarget(self, coordinate):
        if type(coordinate) == GeocacheWrapper:
            c = coordinate._geocache
        elif type(coordinate) == CoordinateWrapper:
            c = coordinate._coordinate
        else:
            logger.debug("Setting Target to None")
            c = None
        #self.settings['last_target_lat'], self.settings['last_target_lon'] = c.lat, c.lon
        self.core.set_target(c)

    @QtCore.Slot(bool, float, float, bool, float, bool, float, float, QtCore.QObject)
    def positionChanged(self, valid, lat, lon, altvalid, alt, speedvalid, speed, error, timestamp):
        if self.callback_gps == None:
            logger.debug("No GPS callback registered")
            return
        if valid:
            p = geo.Coordinate(lat, lon)
        else:
            p = None
        logger.debug("TS is %r" % timestamp)
        a = gpsreader.Fix(position = p,
            altitude = alt if altvalid else None,
            bearing = None,
            speed = speed if speedvalid else None,
            sats = 0,
            sats_known = 0,
            dgps = False,
            quality = 0,
            error = error,
            error_bearing = 0,
            timestamp = timestamp)
        logger.debug("Position changed, new fix is %r" % a)
        self.callback_gps(a)
        
    @QtCore.Slot()
    def uploadFieldnotes(self):
        self.core.on_upload_fieldnotes()

    def _progress(self):
        return self._progress

    def _progress_visible(self):
        return self._progress_visible

    def _progress_message(self):
        return self._progress_message

    progress = QtCore.Property(float, _progress, notify=progressChanged)
    progressVisible = QtCore.Property(bool, _progress_visible, notify=progressChanged)
    progressMessage = QtCore.Property(str, _progress_message, notify=progressChanged)



class MapTypeWrapper(QtCore.QObject):
    def __init__(self, name, url):
        QtCore.QObject.__init__(self)
        self._data_name = name
        self._data_url = url

    def _name(self):
        return self._data_name

    def _url(self):
        return self._data_url

    changed = QtCore.Signal()

    name = QtCore.Property(str, _name, notify=changed)
    url = QtCore.Property(str, _url, notify=changed)

class MapTypesList(QtCore.QAbstractListModel):
    COLUMNS = ('maptype',)

    def __init__(self, maptypes):
        QtCore.QAbstractListModel.__init__(self)
        self.setRoleNames(dict(enumerate(MapTypesList.COLUMNS)))
        #self._maptypes = [{'name': name, 'url': data['remote_url']} for name, data in maptypes]
        self._maptypes = [MapTypeWrapper(name, data['remote_url']) for name, data in maptypes]
        logger.debug("Creating new maptypes list with %d entries" % len(self._maptypes))


    def rowCount(self, parent=QtCore.QModelIndex()):
        return len(self._maptypes)

    def data(self, index, role):
        if index.isValid() and role == MapTypesList.COLUMNS.index('maptype'):
            return self._maptypes[index.row()]
        return None

    def get_data_at(self, i):
        return self._maptypes[i] if i < len(self._maptypes) else None
        
    def get_index_of(self, t):
        try:
            return self._maptypes.index(t)
        except ValueError:
            logger.debug("Map type not found: %r" % t)
            return None

class FixWrapper(QtCore.QObject):

    def __init__(self, fix):
        QtCore.QObject.__init__(self)
        self.data = fix

    changed = QtCore.Signal()
    
    def update(self, fix):
        self.data = fix
        logger.debug("Fix updated with data from %r" % fix)
        self.changed.emit()

    def _lat(self):
        if self.data.position != None:
            return self.data.position.lat
        else:
            return -1

    def _lon(self):
        if self.data.position != None:
            return self.data.position.lon
        else:
            return -1

    def _altitude(self):
        return self.data.altitude if self.data.altitude != None else 0

    def _speed(self):
        return self.data.speed if self.data.speed != None else 0

    def _error(self):
        return float(self.data.error)

    def _valid(self):
        return (self.data.position != None)

    def _altitude_valid(self):
        return self.data.altitude != None

    def _speed_valid(self):
        return self.data.speed != None

    lat = QtCore.Property(float, _lat, notify=changed)
    lon = QtCore.Property(float, _lon, notify=changed)
    altitude = QtCore.Property(float, _altitude, notify=changed)
    speed = QtCore.Property(float, _speed, notify=changed)
    error = QtCore.Property(float, _error, notify=changed)
    valid = QtCore.Property(bool, _valid, notify=changed)
    speedValid = QtCore.Property(bool, _speed_valid, notify=changed)
    altitudeValid = QtCore.Property(bool, _altitude_valid, notify=changed)


class GPSDataWrapper(QtCore.QObject):

    changed = QtCore.Signal()
    changed_target = QtCore.Signal()
    changed_distance_bearing = QtCore.Signal()

    def __init__(self, core):
        QtCore.QObject.__init__(self)
        self.core = core
        self.core.connect('good-fix', self._on_good_fix)
        self.core.connect('no-fix', self._on_no_fix)
        self.core.connect('target-changed', self._on_target_changed)
        self.gps_data = FixWrapper(gpsreader.Fix())
        self.gps_last_good_fix = FixWrapper(gpsreader.Fix())
        self.gps_target_distance = None
        self.gps_target_bearing = None
        self.gps_has_fix = False
        self.gps_status = ''
        self._target_valid = False
        self._target = CoordinateWrapper(geo.Coordinate(0, 0))
        self.astral = Astral()


    def _on_good_fix(self, core, gps_data, distance, bearing):
        logger.debug("Received good fix")
        self.gps_data.update(gps_data)
        self.gps_last_good_fix.update(gps_data)
        self.gps_has_fix = True
        self.gps_target_distance = distance
        self.gps_target_bearing = bearing
        self.changed_distance_bearing.emit()
        self.changed.emit()

    def _on_no_fix(self, caller, gps_data, status):
        self.gps_data.update(gps_data)
        self.gps_has_fix = False
        self.gps_status = status
        self.changed_distance_bearing.emit()
        self.changed.emit()

    def _on_target_changed(self, caller, target, distance, bearing):
        self._target_valid = (target != None)
        self._target = CoordinateWrapper(target) if target != None else CoordinateWrapper(geo.Coordinate(0, 0))
        self.gps_target_distance = distance
        self.gps_target_bearing = bearing
        self.changed_distance_bearing.emit()
        self.changed_target.emit()
        logger.debug("Target is now set to %r" % target)

#    def _sun_angle_valid(self):
#        return self.astral.get_sun_azimuth_from_fix(self.gps_last_good_fix) != None
#

    def _target(self):
        return self._target

    def _target_valid(self):
        return self._target_valid

    def _gps_data(self):
        return self.gps_data

    def _gps_last_good_fix(self):
        return self.gps_last_good_fix

    def _gps_has_fix(self):
        return self.gps_has_fix

    def _gps_target_distance_valid(self):
        return self.gps_target_distance != None

    def _gps_target_distance(self):
        logger.debug("Target distance is %r" % self.gps_target_distance)
        return float(self.gps_target_distance) if self._gps_target_distance_valid()  else 0

    def _gps_target_bearing(self):
        try:
            return float(self.gps_target_bearing)
        except TypeError:
            return 0

    def _gps_status(self):
        return self.gps_status

    data = QtCore.Property(QtCore.QObject, _gps_data, notify=changed)
    lastGoodFix = QtCore.Property(QtCore.QObject, _gps_last_good_fix, notify=changed)
    hasFix = QtCore.Property(bool, _gps_has_fix, notify=changed)
    targetValid = QtCore.Property(bool, _target_valid, notify=changed_target)
    target = QtCore.Property(QtCore.QObject, _target, notify=changed_target)
    targetDistanceValid = QtCore.Property(bool, _gps_target_distance_valid, notify=changed_distance_bearing)
    targetDistance = QtCore.Property(float, _gps_target_distance, notify=changed_distance_bearing)
    targetBearing = QtCore.Property(float, _gps_target_bearing, notify=changed_distance_bearing)
    status = QtCore.Property(str, _gps_status, notify=changed)





class SettingsWrapper(QtCore.QObject):
    def __init__(self, core):
        QtCore.QObject.__init__(self)
        self.core = core
        self.core.connect('settings-changed', self._settings_changed)
        self.core.connect('save-settings', self._save_settings)
        self.settings = {}
        self._map_types_list = MapTypesList(self.core.settings['map_providers'])

    settingsChanged = QtCore.Signal()

    def _setting(self, s, t):
        x = t(self.settings[s]) if s in self.settings else 0
        return x

    def _set_setting(self, s, t, notify = True):
        logger.debug("Setting %s is now: %r" % (s, t))
        self.settings[s] = t
        if notify:
            self.settingsChanged.emit()
        else:
            logger.debug("Not notifying about %s settings change" % s)

    # Handle gobject signal from Core
    def _save_settings(self, caller):
        caller.save_settings(self.settings, self)

    # Handle gobject signal from Core
    def _settings_changed(self, caller, settings, source):
        if source == self:
            return
        logger.debug("Settings object got settings from %s, len() = %d, source = %s" % (caller, len(settings), source))
        self.settings.update(settings)

        if 'map_providers' in settings:
            self._map_types_list = MapTypesList(settings['map_providers'])
        if 'map_type' in settings:
            self._current_map_type = self._map_types_list.get_data_at(settings['map_type'])
            
        #if 'last_target_lat' in settings:
        #    self.setTarget(settings['last_target_lat'], settings['last_target_lon'])

        self.settingsChanged.emit()



    def _distance_unit(self):
        return "m"

    def _coordinate_format(self):
        return "DM"

    def _get_current_map_type(self):
        if 'map_type' in self.settings:
            return self._map_types_list.get_data_at(self.settings['map_type'])
        else:
            return self._map_types_list.get_data_at(0)
        
    def _set_current_map_type(self, map_type):
        self.settings['map_type'] = self._map_types_list.get_index_of(map_type)
        self.settingsChanged.emit()

    def _map_types(self):
        return self._map_types_list

    def createSetting(name, type, signal, inputNotify = True):
        return QtCore.Property(type, lambda x: x._setting(name, type), lambda x, m: x._set_setting(name, m, inputNotify), notify=signal)

    mapPositionLat = createSetting('map_position_lat', float, settingsChanged, False)
    mapPositionLon = createSetting('map_position_lon', float, settingsChanged, False)
    mapZoom = createSetting('map_zoom', int, settingsChanged, False)
    optionsUsername = createSetting('options_username', str, settingsChanged)
    optionsPassword = createSetting('options_password', str, settingsChanged)
    lastSelectedGeocache = createSetting('last_selected_geocache', str, settingsChanged, False)
    optionsMapRotation = createSetting('options_maprotation', bool, settingsChanged)
    optionsHideFound = createSetting('options_hide_found', bool, settingsChanged)
    optionsShowPositionError = createSetting('options_show_position_error', bool, settingsChanged)

    currentMapType = QtCore.Property(QtCore.QObject, _get_current_map_type, _set_current_map_type, notify=settingsChanged)
    mapTypes = QtCore.Property(QtCore.QObject, _map_types, notify=settingsChanged)
    distanceUnit = QtCore.Property(str, _distance_unit, notify=settingsChanged)
    coordinateFormat = QtCore.Property(str, _coordinate_format, notify=settingsChanged)


class CoordinateWrapper(QtCore.QObject):
    def __init__(self, coordinate):
        QtCore.QObject.__init__(self)
        self._coordinate = coordinate
        self._is_valid = (self._coordinate.lat != -1 or self._coordinate.lon != -1) and self._coordinate.lat != None
        if self._is_valid:
            try:
                float(self._coordinate.lat)
                float(self._coordinate.lon)
            except ValueError:
                self._is_valid = false

    def _name(self):
        return self._coordinate.name

    def _lat(self):
        return self._coordinate.lat if self._is_valid else -1

    def _lon(self):
        return self._coordinate.lon if self._is_valid else -1

    def _display_text(self):
        return d(self._coordinate.display_text)

    def _comment(self):
        return d(self._coordinate.comment)

    def _user_coordinate_id(self):
        return self._coordinate.user_coordinate_id

    def _is_valid_coordinate(self):
        return self._is_valid

    changed = QtCore.Signal()

    name = QtCore.Property(str, _name, notify=changed)
    lat = QtCore.Property(float, _lat, notify=changed)
    lon = QtCore.Property(float, _lon, notify=changed)
    display_text = QtCore.Property(str, _display_text, notify=changed)
    comment = QtCore.Property(str, _comment, notify=changed)
    user_coordinate_id = QtCore.Property(unicode, _user_coordinate_id, notify=changed)
    valid = QtCore.Property(bool, _is_valid_coordinate, notify=changed)

class CoordinateListModel(QtCore.QAbstractListModel):
    COLUMNS = ('coordinate',)

    def __init__(self, core, coordinates = []):
        QtCore.QAbstractListModel.__init__(self)
        self._coordinates = coordinates
        self.setRoleNames(dict(enumerate(CoordinateListModel.COLUMNS)))

    def update(self, new):
        self._coordinates = new
        QtCore.QAbstractListModel.dataChanged(self)

    def rowCount(self, parent=QtCore.QModelIndex()):
        return len(self._coordinates)

    def data(self, index, role):
        if index.isValid() and role == CoordinateListModel.COLUMNS.index('coordinate'):
            return self._coordinates[index.row()]
        return None
        

class ImageListModel(QtCore.QAbstractListModel):
    COLUMNS = ('image',)

    def __init__(self, images = []):
        QtCore.QAbstractListModel.__init__(self)
        self._images = images
        self.setRoleNames(dict(enumerate(ImageListModel.COLUMNS)))

    def rowCount(self, parent=QtCore.QModelIndex()):
        return len(self._images)

    def data(self, index, role):
        if index.isValid() and role == ImageListModel.COLUMNS.index('image'):
            logger.debug("Image retrieved: %r and has url '%s'"  % (self._images[index.row()], self._images[index.row()]._url()))
            return self._images[index.row()]
        return None

class ImageWrapper(QtCore.QObject):
    
    def __init__(self, imageUrl, imageName):
        QtCore.QObject.__init__(self)
        self.__url = imageUrl
        self.__name = imageName
        
    def _url(self):
        return self.__url
        
    def _name(self):
        return self.__name
        
    changed = QtCore.Signal()
        
    url = QtCore.Property(str, _url, notify=changed)
    name = QtCore.Property(str, _name, notify=changed)


class GeocacheWrapper(QtCore.QObject):
    def __init__(self, geocache, core):
        QtCore.QObject.__init__(self)
        self._geocache = geocache
        self.core = core
        self._coordinate_list = None
        self._logs_list = None
        self._image_list = None

    def update(self, geocache):
        self._geocache = geocache
        self._coordinate_list = None
        self._logs_list = None
        self._image_list = None
        self.changed.emit()
        
    def _name(self):
        return self._geocache.name

    def _title(self):
        return self._geocache.title

    def _lat(self):
        return self._geocache.lat

    def _lon(self):
        return self._geocache.lon

    def _shortdesc(self):
        return self._geocache.shortdesc

    def _desc(self):
        if self._geocache.desc != '' and self._geocache.shortdesc != '':
            showdesc = "<b>%s</b><br />%s" % (self._geocache.shortdesc, self._geocache.desc)
        elif self._geocache.desc == '' and self._geocache.shortdesc == '':
            showdesc = "<i>No description available</i>"
        elif self._geocache.desc == '':
            showdesc = self._geocache.shortdesc
        else:
            showdesc = self._geocache.desc
        showdesc = re.sub(r'\[\[img:([^\]]+)\]\]', lambda a: "<img src='%s' />" % self.get_path_to_image(a.group(1)), showdesc)
        return showdesc

    def _logs(self):
        if self._logs_list == None:
            logs = self._geocache.get_logs()
            self._logs_list = LogsListModel(self.core, logs)
            logger.debug("Creating logs list... logs: %d" % self._logs_list.rowCount())
        return self._logs_list

    def _logs_count(self):
        return self._logs().rowCount()

    def get_path_to_image(self, image):
        return path.join(self.core.settings['download_output_dir'], image)

    def _type(self):
        return self._geocache.type

    def _size(self):
        return self._geocache.size

    def _difficulty(self):
        return (self._geocache.difficulty/10.0)

    def _terrain(self):
        return (self._geocache.terrain/10.0)

    def _owner(self):
        return self._geocache.owner

    def _found(self):
        return self._geocache.found

    def _hints(self):
        return self._geocache.hints

    def _coordinates(self):
        logger.debug("Preparing coordinate list...")
        if self._coordinate_list == None:
            self._geocache.start_calc()
            z = [CoordinateWrapper(x) for x in self._geocache.get_collected_coordinates(format = geo.Coordinate.FORMAT_DM).values()]
            self._coordinate_list = CoordinateListModel(self.core, z)
        return self._coordinate_list

    def _coordinates_count(self):
        return self._coordinates().rowCount()

    def _images(self):
        if self._image_list == None:
            l = [ImageWrapper(self.get_path_to_image(x), y) for (x, y) in self._geocache.get_images().items()]
            self._image_list = ImageListModel(l)
        return self._image_list

    def _status(self):
        return self._geocache.status

    def _has_details(self):
        return self._geocache.was_downloaded()
        
    def _logas(self):
        try:
            return int(self._geocache.logas)
        except ValueError:
            return 0
        
    def _fieldnotes(self):
        return self._geocache.fieldnotes
    
    @QtCore.Slot(str, str)
    def setFieldnote(self, logas, text):
        from time import gmtime
        from time import strftime
        logger.debug("Setting fieldnote, logas=%r, text=%r" % (logas, text))
        self._geocache.logas = logas
        self._geocache.fieldnotes = text
        self._geocache.logdate = strftime('%Y-%m-%d', gmtime())
        self.core.save_fieldnote(self._geocache)
        self.changed.emit()

    changed = QtCore.Signal()

    name = QtCore.Property(str, _name, notify=changed)
    title = QtCore.Property(unicode, _title, notify=changed)
    lat = QtCore.Property(float, _lat, notify=changed)
    lon = QtCore.Property(float, _lon, notify=changed)
    desc = QtCore.Property(str, _desc, notify=changed)
    shortdesc = QtCore.Property(str, _shortdesc, notify=changed)
    type = QtCore.Property(str, _type, notify=changed)
    size = QtCore.Property(int, _size, notify=changed)
    difficulty = QtCore.Property(float, _difficulty, notify=changed)
    terrain = QtCore.Property(float, _terrain, notify=changed)
    owner = QtCore.Property(str, _owner, notify=changed)
    found = QtCore.Property(bool, _found, notify=changed)
    images = QtCore.Property(QtCore.QObject, _images, notify=changed)
    status = QtCore.Property(int, _status, notify=changed)
    logs = QtCore.Property(QtCore.QObject, _logs, notify=changed)
    logsCount = QtCore.Property(int, _logs_count, notify=changed)
    coordinates = QtCore.Property(QtCore.QObject, _coordinates, notify=changed)
    coordinatesCount = QtCore.Property(int, _coordinates_count, notify=changed)
    hasDetails = QtCore.Property(bool, _has_details, notify=changed)
    hints = QtCore.Property(str, _hints, notify=changed)
    logas = QtCore.Property(int, _logas, notify=changed)
    fieldnotes = QtCore.Property(str, _fieldnotes, notify=changed)

class GeocacheListModel(QtCore.QAbstractListModel):
    COLUMNS = ('geocache',)

    def __init__(self, core, lat_start, lon_start, lat_end, lon_end):
        logger.debug("1. Initializing qabstract...")
        QtCore.QAbstractListModel.__init__(self)
        logger.debug("2. Creating list...")
        k = core.pointprovider.get_points(geo.Coordinate(lat_start, lon_start), geo.Coordinate(lat_end, lon_end), 1000) #[0:100]
        logger.debug("3. Wrapping coordinates...")
        self._geocaches = [GeocacheWrapper(x, core) for x in k]
        self.setRoleNames(dict(enumerate(GeocacheListModel.COLUMNS)))

        logger.debug("4. Loaded %d geocaches for %f-%f %f-%f" % (len(self._geocaches), lat_start, lon_start, lat_end, lon_end))

    def rowCount(self, parent=QtCore.QModelIndex()):
        return len(self._geocaches)

    def data(self, index, role):
        #if index.isValid() and role == GeocacheListModel.COLUMNS.index('geocache'):
        return self._geocaches[index.row()]
        #return None


class LogsListModel(QtCore.QAbstractListModel):
    COLUMNS = ('log',)

    def __init__(self, core, logs = []):
        QtCore.QAbstractListModel.__init__(self)
        self._logs = [LogWrapper(x) for x in logs]
        self.setRoleNames(dict(enumerate(LogsListModel.COLUMNS)))


    def rowCount(self, parent=QtCore.QModelIndex()):
        return len(self._logs)

    def data(self, index, role):
        if index.isValid() and role == LogsListModel.COLUMNS.index('log'):
            return self._logs[index.row()]
        return None

class LogWrapper(QtCore.QObject):
    ICONS = {
        geocaching.GeocacheCoordinate.LOG_TYPE_FOUND: 'emoticon_grin',
        geocaching.GeocacheCoordinate.LOG_TYPE_NOTFOUND: 'cross',
        geocaching.GeocacheCoordinate.LOG_TYPE_NOTE: 'comment',
        geocaching.GeocacheCoordinate.LOG_TYPE_MAINTENANCE: 'wrench',
        geocaching.GeocacheCoordinate.LOG_TYPE_PUBLISHED: 'accept',
        geocaching.GeocacheCoordinate.LOG_TYPE_DISABLED: 'delete',
        geocaching.GeocacheCoordinate.LOG_TYPE_NEEDS_MAINTENANCE: 'error',
        geocaching.GeocacheCoordinate.LOG_TYPE_WILLATTEND: 'calendar_edit',
        geocaching.GeocacheCoordinate.LOG_TYPE_ATTENDED: 'group',
        geocaching.GeocacheCoordinate.LOG_TYPE_UPDATE: 'asterisk_yellow',
    }
    
    changed = QtCore.Signal()
    def __init__(self, log):
        QtCore.QObject.__init__(self)
        self._log = log

    def _type(self):
        logger.debug('type')
        if self._log['type'] == geocaching.GeocacheCoordinate.LOG_TYPE_FOUND:
            t = 'FOUND'
        elif self._log['type'] == geocaching.GeocacheCoordinate.LOG_TYPE_NOTFOUND:
            t = 'NOT FOUND'
        elif self._log['type'] == geocaching.GeocacheCoordinate.LOG_TYPE_NOTE:
            t = 'NOTE'
        elif self._log['type'] == geocaching.GeocacheCoordinate.LOG_TYPE_MAINTENANCE:
            t = 'MAINTENANCE'
        else:
            t = self._log['type'].upper()
        return t

    def _finder(self):
        return self._log['finder']

    def _year(self):
        return self._log['year']

    def _month(self):
        return self._log['month']

    def _day(self):
        return self._log['day']

    def _text(self):
        return self._log['text']

    def _icon_basename(self):
        r = self.ICONS[self._log['type']] if self._log['type'] in self.ICONS else ""
        return r

    type = QtCore.Property(str, _type, notify=changed)
    finder = QtCore.Property(str, _finder, notify=changed)
    year = QtCore.Property(str, _year, notify=changed)
    month = QtCore.Property(str, _month, notify=changed)
    day = QtCore.Property(str, _day, notify=changed)
    text = QtCore.Property(str, _text, notify=changed)
    iconBasename = QtCore.Property(str, _icon_basename, notify=changed)
    
    

class QmlGui(Gui):

    USES = ['geonames', 'qmllocationprovider']

    def __init__(self, core, dataroot, parent=None):
        self.app = QtGui.QApplication(sys.argv)
        self.core = core
        self.view = QtDeclarative.QDeclarativeView()
        self.view.statusChanged.connect(self._status_changed)
        glw = QtOpenGL.QGLWidget()
        self.view.setViewport(glw)
        
        self.controller = Controller(self.view, self.core)
        settings = SettingsWrapper(self.core)
        #geocacheList = GeocacheListModel(self.core)

        rc = self.view.rootContext()
        rc.setContextProperty('controller', self.controller)
        rc.setContextProperty('settings', settings)
        rc.setContextProperty('gps', GPSDataWrapper(self.core))
        #rc.setContextProperty('geocacheList', geocacheList)
        #rc.setContextProperty('geocacheList', 42)

        self.view.setSource(os.path.join('qml','main.qml'))

    def get_gps(self, callback):
        self.controller.callback_gps = callback

    def show(self):
        self.view.showFullScreen()
        self.app.exec_()
        self.core.on_destroy()

    def _status_changed(self, error):
        logger.error(self.view.errors())
