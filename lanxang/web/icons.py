"""
Small line icons for the web pages, drawn in the text colour so they follow the light and dark themes (emoji
don't). icon("server") returns an inline <svg>; unknown names fall back to "info".
"""

PATHS = {
    "server": '<rect x="3" y="4" width="18" height="7" rx="2"/><rect x="3" y="13" width="18" height="7" rx="2"/>'
              '<path d="M7 7.5h.01M7 16.5h.01"/>',
    "laptop": '<rect x="5" y="5" width="14" height="10" rx="1"/><path d="M3 19h18"/>',
    "phone": '<rect x="7" y="3" width="10" height="18" rx="2"/><path d="M11 17h2"/>',
    "tv": '<rect x="3" y="5" width="18" height="12" rx="2"/><path d="M8 21h8"/>',
    "bulb": '<path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9V16h7v-2.1A6 6 0 0 0 12 3z"/>',
    "antenna": '<circle cx="12" cy="10" r="1.5"/><path d="M12 12v9M8.5 6.5a5 5 0 0 0 0 7M15.5 6.5a5 5 0 0 1 0 7'
               'M5.5 4a9 9 0 0 0 0 12M18.5 4a9 9 0 0 1 0 12"/>',
    "help": '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .8-1 1.5V14M12 17h.01"/>',
    "globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18a14 14 0 0 1 0-18"/>',
    "lock": '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    "shield": '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/>',
    "home": '<path d="M3 11l9-7 9 7M5 10v10h14V10"/>',
    "gear": '<circle cx="12" cy="12" r="3"/><path d="M21.3 9.9L21.3 14.1L18.6 14.5L18.4 14.9L20.0 17.1L17.1 20.0L14.9 18.4L14.5 18.6L14.1 21.3L9.9 21.3L9.5 18.6L9.1 18.4L6.9 20.0L4.0 17.1L5.6 14.9L5.4 14.5L2.7 14.1L2.7 9.9L5.4 9.5L5.6 9.1L4.0 6.9L6.9 4.0L9.1 5.6L9.5 5.4L9.9 2.7L14.1 2.7L14.5 5.4L14.9 5.6L17.1 4.0L20.0 6.9L18.4 9.1L18.6 9.5z"/>',
    "plug": '<path d="M9 3v5M15 3v5M6 8h12v3a6 6 0 0 1-12 0zM12 17v4"/>',
    "alert": '<path d="M12 4 2.5 20h19zM12 10v4M12 17h.01"/>',
    "tool": '<path d="M14.5 4a4.5 4.5 0 0 0 5.5 5.5L11 18.5a2.1 2.1 0 0 1-3-3L17 6.5"/>',
    "refresh": '<path d="M20 11a8 8 0 0 0-14-5L4 8M4 4v4h4M4 13a8 8 0 0 0 14 5l2-2M20 20v-4h-4"/>',
    "chat": '<path d="M4 5h16v11H9l-5 4z"/>',
    "search": '<circle cx="11" cy="11" r="6"/><path d="M20 20l-4.5-4.5"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
    "key": '<circle cx="8" cy="15" r="4"/><path d="M11 12l9-9M17 6l2 2M15 8l2 2"/>',
    "bolt": '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4'
           'M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "box": '<path d="M3 7.5 12 3l9 4.5v9L12 21l-9-4.5zM3 7.5 12 12l9-4.5M12 12v9"/>',
    "moon": '<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/>',
    "monitor": '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
    "network": '<rect x="9" y="3" width="6" height="5" rx="1"/><rect x="3" y="16" width="6" height="5" rx="1"/>'
               '<rect x="15" y="16" width="6" height="5" rx="1"/><path d="M12 8v4M6 16v-4h12v4"/>',
    "logout": '<path d="M10 4H5v16h5M14 8l4 4-4 4M18 12H9"/>',
    "sidebar": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16M15 10l-2 2 2 2"/>',
}


def icon(name):

    return ('<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{PATHS.get(name, PATHS["info"])}</svg>')
