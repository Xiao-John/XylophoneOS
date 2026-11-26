# SPDX-License-Identifier: Apache-2.0
# Exercise the path check with an amended copy of the real imported target.
macro(find_package)
    _find_package(${ARGV})
    if ("${ARGV0}" STREQUAL "LibXml2" AND TARGET LibXml2::LibXml2)
        set_property(TARGET LibXml2::LibXml2 APPEND PROPERTY
                     INTERFACE_INCLUDE_DIRECTORIES "${XOS_XML_EXTRA_INCLUDE}")
    endif()
endmacro()
