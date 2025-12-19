# Prompt for LLM Agent: USPS District Map Module

**Role:** You are an expert Drupal 10/11 Backend and Frontend Developer.

**Task:** Create a new custom Drupal module named `usps_district_map` and a deployment script to install it on a remote server.

**Context:**
The goal is to create a form where a user enters an US address. The system must validate the address with USPS, find its geolocation and Congressional District, and then display it on a map with the specific Congressional District's shapefile (KML) overlaid.

**Key Challenges & Solutions:**
1.  **Address Validation**: Use the USPS Web Tools API (OAuth 2.0).
2.  **District Lookup**: The USPS API *does not* return the Congressional District. You must implement a bridge service using the **US Census Bureau Geocoder API** (Free) to take the validated address and retrieve the `State FIPS` and `Congressional District FIPS` codes.
3.  **Visualization**: Use Leaflet.js to pinpoint the location and load the specific KML file (e.g., `districts/36_14.kml`) that matches the FIPS codes.

**Requirements:**

1.  **Module Configuration (`usps_district_map.settings`)**:
    *   `usps_client_id`: USPS OAuth Client ID.
    *   `usps_client_secret`: USPS OAuth Client Secret.
    *   `kml_directory`: Path to the directory where KML files are stored (default: `public://congressional-districts/`).

2.  **Services**:
    *   `UspsValidatorService`: Handles OAuth token retrieval and Address Validation via USPS API.
    *   `CensusGeocoderService`: Takes a standard address, queries the [Census Geocoder API](https://geocoding.geo.census.gov/geocoder/geographies/address), and returns:
        *   Latitude/Longitude.
        *   State FIPS (e.g., "06" for CA).
        *   District FIPS (e.g., "12" for 12th District).

3.  **User Form**:
    *   A form with standard address fields (Street, City, State, Zip).
    *   AJAX submit handler that:
        1.  Validates via `UspsValidatorService`.
        2.  Geocodes via `CensusGeocoderService`.
        3.  Returns the Map render array.

4.  **Frontend (Leaflet)**:
    *   Initialize a Leaflet map.
    *   Add a standard OpenStreetMap tile layer.
    *   Add a **Marker** at the returned Lat/Long.
    *   Add a **KML Layer**: Load the specific KML file based on the returned FIPS codes (e.g., `[StateFIPS]_[DistrictFIPS].kml`). Use a library like `leaflet-plugins/layer/vector/KML.js` or generic KML parsing.

5.  **Deployment Script**:
    *   Review the existing script `scripts/update_cat_descriptions.py` to understand how this project handles SSH connections (Host, User, Password, Hostkey).
    *   Create a new script `scripts/deploy_usps_module.py` that:
        *   Connects to the server using `plink.exe`/`pscp.exe` (as seen in the reference script).
        *   Uploads the `drupal_modules/usps_district_map` directory to `/var/www/drupal/web/modules/custom/`.
        *   Runs `drush en usps_district_map -y` and `drush cr` remotely.

**Implementation Details:**
*   Develop the module locally in `drupal_modules/usps_district_map`.
*   Ensure strict dependency injection for all Drupal services.
*   Assume the KML files are named `[StateFIPS]_[DistrictFIPS].kml` (e.g., `36_14.kml` for NY District 14).
*   Use Drupal's `HttpClient` for all API calls.

**Deliverables:**
1.  Complete Drupal module code.
2.  `deploy_usps_module.py` python script.
