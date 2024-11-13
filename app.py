import ee
import pandas as pd
import numpy as np
import geemap
import ipyleaflet
from shiny import App, render, ui, reactive
from shinywidgets import output_widget, render_widget

# Initialize Earth Engine
ee.Initialize(project='ceo-nightlights')

# Define the Shiny app
app_ui = ui.page_fluid(
    ui.card(
        ui.h2("China Nightlight Radiance Data with Map and Table")
    ),
    ui.layout_column_wrap(
        ui.card(
            # Sidebar with inputs only
            ui.input_select("start_year", "Start Year", [2024, 2025]),
            ui.input_select("start_month", "Start Month", [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]),
        ),
        ui.card(
            # Sidebar with inputs only
            ui.input_select("end_year", "End Year", [2024, 2025]),
            ui.input_select("end_month", "End Month", [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]),
        )
    ),
    ui.card(
        ui.output_text_verbatim("info"),
        ui.input_action_button("update", "Update")
    ),
    # Main panel with outputs
    ui.layout_column_wrap(
        ui.card(
            ui.output_data_frame("table")  # Output the table here
        ),
        ui.card(
            output_widget("map")  # Output the map here
        )
    )
)

# Function to create a color map for positive/negative values
def create_colormap(percentage_changes):
    # Define color mapping from blue (negative) to red (positive)
    colors = [(0, 0, 255), (1, 0, 0)]  # Blue to Red
    norm_changes = np.array(percentage_changes)  # Normalize the changes for colormap
    norm_changes = np.interp(norm_changes, (min(norm_changes), max(norm_changes)), (0, 1))  # Normalize to [0,1]
    
    # Create RGB values for each percentage change
    colormap_values = [(int(c[0] * 255), int(c[1] * 255), int(c[2] * 255)) for c in 
                       np.linspace(colors[0], colors[1], len(norm_changes))]
    
    # Convert RGB to hex color code
    hex_colors = ["#{:02x}{:02x}{:02x}".format(rgb[0], rgb[1], rgb[2]) for rgb in colormap_values]
    
    return hex_colors

def server(input, output, session):
    @reactive.Calc
    @reactive.event(input.update)
    def fetch_data():
        # Get the selected start and end year and month from the UI
        start_year = int(input.start_year())
        start_month = int(input.start_month())
        end_year = int(input.end_year())
        end_month = int(input.end_month())

        # Define the start and end dates for the selected months
        start_date = f"{start_year}-{start_month:02d}-01"
        end_date = f"{end_year}-{end_month:02d}-01"

        # Load the China states feature collection
        china_states = ee.FeatureCollection("FAO/GAUL/2015/level1") \
            .filter(ee.Filter.eq("ADM0_NAME", "China"))

        # Load the Nightlights image collection for the specified date range for the start month
        nightlights_start = ee.ImageCollection("NOAA/VIIRS/DNB/MONTHLY_V1/VCMCFG") \
            .filter(ee.Filter.date(start_date, f"{start_year}-{start_month:02d}-28")) \
            .select("avg_rad")

        # Load the Nightlights image collection for the specified date range for the end month
        nightlights_end = ee.ImageCollection("NOAA/VIIRS/DNB/MONTHLY_V1/VCMCFG") \
            .filter(ee.Filter.date(end_date, f"{end_year}-{end_month:02d}-28")) \
            .select("avg_rad")

        # Check if the collections are empty
        if nightlights_start.size().getInfo() == 0 or nightlights_end.size().getInfo() == 0:
            return pd.DataFrame({"Error": [f"No data available for the selected months."]})

        # Create mosaics of nightlights and clip them to China states
        mosaic_start = nightlights_start.mosaic().clip(china_states)
        mosaic_end = nightlights_end.mosaic().clip(china_states)

        # Reduce regions to compute mean radiance within each China state for both start and end months
        average_radiance_start = mosaic_start.reduceRegions(
            collection=china_states,
            reducer=ee.Reducer.mean(),
            scale=1000
        )

        average_radiance_end = mosaic_end.reduceRegions(
            collection=china_states,
            reducer=ee.Reducer.mean(),
            scale=1000
        )

        # Extract the results for both start and end months
        features_start = average_radiance_start.getInfo()["features"]
        features_end = average_radiance_end.getInfo()["features"]

        data = []
        percentage_changes = []

        # Loop through the features to structure the data properly
        for start_feature, end_feature in zip(features_start, features_end):
            state_name = start_feature["properties"]["ADM1_NAME"]
            start_mean_radiance = start_feature["properties"].get("mean", None)
            end_mean_radiance = end_feature["properties"].get("mean", None)

            # Calculate the percentage change (if both values are available)
            if start_mean_radiance and end_mean_radiance:
                percentage_change = ((end_mean_radiance - start_mean_radiance) / start_mean_radiance) * 100
            else:
                percentage_change = None

            data.append({
                "State": state_name,
                "Start Mean Radiance": start_mean_radiance,
                "End Mean Radiance": end_mean_radiance,
                "Percentage Change": percentage_change
            })

            if percentage_change is not None:
                percentage_changes.append(percentage_change)

        # Create a colormap based on percentage changes
        hex_colors = create_colormap(percentage_changes)

        Map = geemap.Map(center=(35.0, 105.0), zoom=5)

        # Return both the table and the map widget
        return pd.DataFrame(data), Map

    @output
    @render.text
    def info():
        return f"Showing data for {int(input.start_year())} - {int(input.start_month()):02d} to {int(input.end_year())} - {int(input.end_month()):02d}"

    @output
    @render.data_frame
    def table():
        data, _ = fetch_data()  # Get the data frame
        return data

    @output
    @render_widget
    def map():
        _, Map = fetch_data()
        return Map  

# Run the app
app = App(app_ui, server)