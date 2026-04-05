# Freeview XMLTV EPG Generator
This repository pulls the official Freeview Guide and generates highly optimized, universally compatible XMLTV files for use in IPTV players like Plex, Jellyfin, Emby, and TiviMate. These should be a direct match for live TV in the region.

## Features
* **Strict UTC Timezones:** Automatically converts all local broadcast times into pure UTC (`+0000`) to eliminate Daylight Saving Time bugs across all media servers.
* **LCN Injection:** Injects official Logical Channel Numbers to sort the guide accurately.
* **Smart Logo Handling:** Downloads static channel logos
* **Program images:** links directly to programme images, includes fallback image logic for radio/talk shows.
* **Intelligent Caching:** caches metadata from previous runs speeding up execution.
* **Advanced Genre Mapping:** Translates broadcaster to standard categories (e.g., "Movie", "News", "Sports") to enable native color-coding and filtering.
	* `0`: Shopping
	* `1`: Movie, Film
	* `2`: News, Factual, Documentary
	* `3`: Entertainment, Comedy, Game Show
	* `4`: Sports
	* `5`: Children, Kids
	* `6`: Music
	* `7`: Lifestyle, Reality
	* `8`: Drama, Soap
	* `9`: Arts, Education

---

## How the Code Works (The 4 Passes)

### **Pass 0: Channel Mapping & Logos**
* **Action:** Pulls the main channel list.
* **Data Gathered:** Channel ID, Display Name, Logical Channel Number (LCN), and channel's master logo.
* **Processing:** Pulls the channel logo if not already saved.

### **Pass 1: Schedule Builder**
* **Action:** Pulls and processes 8 days of data.
* **Data Gathered:** Programme ID, Main Title, Start Time, Duration, Main Image URL, Fallback Image URL, and Genre.
* **Processing:** Calculates program start and end times and identifies which programmes require metadata to be pulled.

### **Pass 2: Metadata Fetch**
* **Action:** Pulls non-cached metadata.
* **Data Gathered:** Episode titles, long descriptions, Subtitle availability, and Audio Description (AD) flags.
* **Processing:** Saves the results to the cache.

### **Pass 3: XML Generation**
* **Action:** Combines the channel data, schedule data, and metadata into the final XMLTV output.
* **Processing:** Sanitizes all text, maps genres, and writes the `xml` file locally.
