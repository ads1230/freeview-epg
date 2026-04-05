# Freeview XMLTV EPG Generator

This repository contains automated Python scripts designed to scrape the official Freeview Guide APIs. It processes the raw JSON data and generates highly optimized, universally compatible XMLTV (`.xml`) files for use in IPTV players like Plex, Jellyfin, Emby, and TiviMate.

## Features

* **Strict UTC Timezones:** Automatically converts all local broadcast times into pure UTC (`+0000`) to eliminate Daylight Saving Time bugs across all media servers.
* **LCN Injection:** Injects official Logical Channel Numbers (`<lcn>`) so your channels sort accurately in your guide.
* **Smart Logo Handling:** Downloads static channel logos directly to this repository to bypass aggressive CDN blocking, while linking directly to dynamically sized high-res programme images (`?w=800`). Includes fallback image logic for radio/talk shows.
* **Advanced Genre Mapping:** Translates proprietary broadcaster codes into standard categories (e.g., "Movie", "News", "Sports") to enable native color-coding and filtering in Plex and Jellyfin.
* **Intelligent Caching:** Uses local `.json` cache files to remember deep metadata from previous runs, significantly speeding up execution and preventing API rate limits.

---

## How the Code Works (The 4 Passes)

Both the Freeview (`epg_script.py`) and Freely (`freely_script.py`) scripts operate using a highly structured "4-Pass" pipeline to ensure data integrity and speed.

### **Pass 0: Channel Mapping & Logos**
* **Action:** Connects to the main channel list API endpoint.
* **Data Gathered:** Channel ID, Display Name, Logical Channel Number (LCN), and the URL for the channel's master logo.
* **Processing:** If the channel logo does not exist in the local `/logos` folder, the script downloads it.

### **Pass 1: The Schedule Builder**
* **Action:** Loops through the next 8 days of TV guide data.
* **Data Gathered:** Programme ID, Main Title, Start Time, Duration, Main Image URL, Fallback Image URL, and the raw Genre URN.
* **Processing:** Calculates the exact end time using the duration, converts both start and stop times to pure UTC, and identifies which programmes require a "deep fetch" for extra metadata.

### **Pass 2: Deep Metadata Fetch (Multithreaded)**
* **Action:** For any programme ID not already stored in the local cache file, the script pings the deep-details API endpoint. It uses `concurrent.futures` to run 4 requests simultaneously for massive speed gains.
* **Data Gathered (Freeview):** Sub-titles (episode titles), long descriptions, Subtitle availability, and Audio Description (AD) flags.
* **Data Gathered (Freely):** Series numbers, Episode numbers, and long descriptions.
* **Processing:** Saves the results to the cache file so it never has to ping the API for that specific episode again.

### **Pass 3: XML Generation**
* **Action:** Combines the channel data, schedule data, and deep metadata into the final XMLTV output.
* **Processing:** Sanitizes all text (HTML escaping, removing hidden control characters), maps the genres, and writes the `xml` file locally.

---

## Data Formatting & Output

The scripts output data strictly adhering to the **XMLTV Standard**. 

### Date and Time Format
Times are formatted as `YYYYMMDDHHMMSS +0000`. By excluding local timezone offsets (like `+0100` for BST), the script relies on the end-user's media player (e.g., Plex) to automatically adjust the times to their local device clock.

### Genre & Category Mapping
The Freeview and Freely APIs do not use standard text for genres. Instead, they use the **Freeview Play Metadata Scheme** (e.g., `urn:fvc:metadata:cs:ContentSubjectCS:2014-07:3`). 

The script intercepts these numerical "nibbles" and translates them using a custom dictionary. To achieve **"Gold Standard" XMLTV compliance**, combined genres are split into individual tags (e.g., rather than `<category>Movie / Drama</category>`, it outputs `<category>Movie</category>` and `<category>Drama</category>`).

**The active mapping schema:**
* `0` ➔ Shopping
* `1` ➔ Movie, Film
* `2` ➔ News, Factual, Documentary
* `3` ➔ Entertainment, Comedy, Game Show
* `4` ➔ Sports
* `5` ➔ Children, Kids
* `6` ➔ Music
* `7` ➔ Lifestyle, Reality
* `8` ➔ Drama, Soap
* `9` ➔ Arts, Education
