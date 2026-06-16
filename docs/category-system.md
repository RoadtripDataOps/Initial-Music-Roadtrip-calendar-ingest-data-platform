# Category System — Music Roadtrip Data Model

## Purpose

This document defines the canonical category system used to interpret Mapotic export data.

This is a **source of truth** for:
- parsing logic
- dataset splitting (POIs vs Events)
- validation rules
- downstream automation

This logic is considered stable unless explicitly updated.

---

## Core Rule: Events vs POIs

### Concert (CRITICAL RULE)

Any row where:

Category = Concert

is ALWAYS an **event**

These records:
- originate from APIs (Jambase, CitySpark, future ticketing sources)
- must be parsed into the **events dataset**
- should NEVER be treated as POIs

This is the primary and most reliable signal for identifying events.

---

## POI Categories

All non-Concert categories represent **music-related points of interest (POIs)**.

Every POI contains some form of music signal.

---

## Main Categories

The following values appear in the `Category` column:

- Concert
- Music Site
- Bars & Lounges
- Cultural
- Food & Bev
- Shopping
- Visitor & Travel
- Lodging

---

## Subcategory System

Subcategories are NOT stored in the main `Category` column.

Instead:
- Each main category has its own **dedicated column**
- That column contains the subcategory value

Example:
- Category = Music Site
- Column = "Music Site"
- Value = "Recording Studio"

---

## Subcategories by Category

### 1. Music Site

Column: `Music Site`

Values:
- Festivals
- Recording Studios
- Radio Stations
- Music Education
- Dance Clubs
- Venues

---

### 2. Cultural

Column: `Cultural`

Values:
- Museums
- Art
- Memorials
- Birthplaces
- Theatres
- Album Covers
- Performing Arts Centers

---

### 3. Food & Bev

Column: `Food & Bev`

Values:
- Restaurants
- Coffee Shops

---

### 4. Shopping

Column: `Shopping`

Values:
- Record Stores
- Music Stores
- Apparel & Merch Shops

---

### 5. Visitor & Travel

Column: `Visitor & Travel`

Values:
- Travel & Tourism
- Chamber

---

### 6. Lodging

Column: `Lodging`

Values:
- Music Hotels
- Music Camping

---

### 7. Bars & Lounges

Currently:
- No subcategories

Important:
- This may change in the future
- If subcategories are introduced, this document must be updated

---

## Key Parsing Logic Summary

- Category = Concert → Event
- Category ≠ Concert → POI

For POIs:
- Main category = `Category`
- Subcategory = value in corresponding category column

---

## Notes

- This structure is stable and intentional
- This logic should be used for all parsing and validation
- Any deviation should be treated as a data issue

---

## Future Considerations

- Additional ticketing APIs will still map to `Concert`
- Subcategory expansion may occur
- Validation rules will enforce category/subcategory consistency