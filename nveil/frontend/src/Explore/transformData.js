// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

const transformCategories = [
  {
    id: "filtering",
    nameKey: "explore.toolkit.filtering",
    icon: "FaFilter",
    transforms: [
      { name: "filter_less_than", descKey: "explore.toolkit.filterLessThanDesc", prompt: "Keep only rows where Price is less than 100" },
      { name: "filter_greater_than", descKey: "explore.toolkit.filterGreaterThanDesc", prompt: "Keep rows where Revenue exceeds 50000" },
      { name: "filter_in_range", descKey: "explore.toolkit.filterInRangeDesc", prompt: "Filter rows where Age is between 18 and 65" },
      { name: "filter_equal", descKey: "explore.toolkit.filterEqualDesc", prompt: "Keep only rows where Country equals 'France'" },
      { name: "filter_not_equal", descKey: "explore.toolkit.filterNotEqualDesc", prompt: "Remove rows where Status is 'cancelled'" },
    ],
  },
  {
    id: "topBottom",
    nameKey: "explore.toolkit.topBottom",
    icon: "FaSortAmountDown",
    transforms: [
      { name: "get_top_n", descKey: "explore.toolkit.getTopNDesc", prompt: "Show the top 10 products by sales" },
      { name: "get_top_percentage", descKey: "explore.toolkit.getTopPctDesc", prompt: "Keep the top 5% of customers by revenue" },
      { name: "get_bottom_n", descKey: "explore.toolkit.getBottomNDesc", prompt: "Show the 5 lowest-performing stores" },
      { name: "get_bottom_percentage", descKey: "explore.toolkit.getBottomPctDesc", prompt: "Get the bottom 10% of scores" },
    ],
  },
  {
    id: "aggregation",
    nameKey: "explore.toolkit.aggregation",
    icon: "FaCalculator",
    transforms: [
      { name: "aggregate_mean", descKey: "explore.toolkit.aggMeanDesc", prompt: "Calculate average salary by department" },
      { name: "aggregate_count", descKey: "explore.toolkit.aggCountDesc", prompt: "Count orders per customer" },
      { name: "aggregate_sum", descKey: "explore.toolkit.aggSumDesc", prompt: "Sum total revenue by region" },
      { name: "aggregate_median", descKey: "explore.toolkit.aggMedianDesc", prompt: "Get the median price per category" },
    ],
  },
  {
    id: "columnOps",
    nameKey: "explore.toolkit.columnOps",
    icon: "FaColumns",
    transforms: [
      { name: "select_columns", descKey: "explore.toolkit.selectColumnsDesc", prompt: "Keep only the Name, Age, and City columns" },
      { name: "drop_columns", descKey: "explore.toolkit.dropColumnsDesc", prompt: "Remove the internal ID column" },
      { name: "rename_column", descKey: "explore.toolkit.renameColumnDesc", prompt: "Rename 'qty' to 'Quantity'" },
      { name: "add_label", descKey: "explore.toolkit.addLabelDesc", prompt: "Add a column 'Source' with value 'Survey 2024'" },
    ],
  },
  {
    id: "rowOps",
    nameKey: "explore.toolkit.rowOps",
    icon: "FaListOl",
    transforms: [
      { name: "count_rows", descKey: "explore.toolkit.countRowsDesc", prompt: "How many rows are in the dataset?" },
      { name: "slice_rows", descKey: "explore.toolkit.sliceRowsDesc", prompt: "Take the first 100 rows" },
      { name: "sort_values", descKey: "explore.toolkit.sortValuesDesc", prompt: "Sort by Date descending" },
      { name: "sample_rows", descKey: "explore.toolkit.sampleRowsDesc", prompt: "Take a random sample of 200 rows" },
    ],
  },
  {
    id: "calculations",
    nameKey: "explore.toolkit.calculations",
    icon: "FaSquareRootVariable",
    transforms: [
      { name: "calc_distance", descKey: "explore.toolkit.calcDistanceDesc", prompt: "Calculate the distance between two lat/lon columns" },
      { name: "calc_ratio", descKey: "explore.toolkit.calcRatioDesc", prompt: "Compute profit margin as Profit / Revenue" },
      { name: "arithmetic_op", descKey: "explore.toolkit.arithmeticOpDesc", prompt: "Create a Total column as Price * Quantity" },
      { name: "normalize_column", descKey: "explore.toolkit.normalizeDesc", prompt: "Normalize the Score column to 0-1 range" },
      { name: "discretize", descKey: "explore.toolkit.discretizeDesc", prompt: "Bucket Age into groups: 0-18, 18-35, 35-65, 65+" },
    ],
  },
  {
    id: "multiInput",
    nameKey: "explore.toolkit.multiInput",
    icon: "FaCodeMerge",
    transforms: [
      { name: "join", descKey: "explore.toolkit.joinDesc", prompt: "Join sales data with customer details on CustomerID" },
      { name: "union", descKey: "explore.toolkit.unionDesc", prompt: "Stack Q1 and Q2 data together" },
      { name: "melt", descKey: "explore.toolkit.meltDesc", prompt: "Unpivot monthly columns into a single Month + Value pair" },
    ],
  },
  {
    id: "timeSeries",
    nameKey: "explore.toolkit.timeSeries",
    icon: "FaClock",
    transforms: [
      { name: "extract_date_part", descKey: "explore.toolkit.extractDatePartDesc", prompt: "Extract the month and year from the Date column" },
      { name: "rolling_statistics", descKey: "explore.toolkit.rollingStatsDesc", prompt: "Add a 7-day rolling average of Sales" },
      { name: "lag_lead", descKey: "explore.toolkit.lagLeadDesc", prompt: "Add a column with yesterday's temperature" },
      { name: "offset_datetime", descKey: "explore.toolkit.offsetDatetimeDesc", prompt: "Shift all dates forward by 1 hour" },
      { name: "forecast_time_series", descKey: "explore.toolkit.forecastDesc", prompt: "Forecast the next 30 days of sales" },
    ],
  },
  {
    id: "geographic",
    nameKey: "explore.toolkit.geographic",
    icon: "FaGlobe",
    transforms: [
      { name: "geocode_location", descKey: "explore.toolkit.geocodeDesc", prompt: "Geocode city names to lat/lon coordinates" },
      { name: "get_country_contours", descKey: "explore.toolkit.countryContoursDesc", prompt: "Get country boundaries for a choropleth map" },
    ],
  },
  {
    id: "advanced",
    nameKey: "explore.toolkit.advanced",
    icon: "FaWandMagicSparkles",
    transforms: [
      { name: "flatten_json", descKey: "explore.toolkit.flattenJsonDesc", prompt: "Flatten nested JSON into columns" },
      { name: "hierarchical_rollup", descKey: "explore.toolkit.hierarchicalDesc", prompt: "Roll up data into a hierarchical tree" },
      { name: "execute_code", descKey: "explore.toolkit.executeCodeDesc", prompt: "Run custom Python code on the data" },
    ],
  },
];

export default transformCategories;
