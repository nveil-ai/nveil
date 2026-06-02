# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Clément Baraille
# SPDX-License-Identifier: AGPL-3.0-or-later

import pandas as pd


def aggregate_by_unique_values(df, column, func='avg'):
    """
    Aggregate DataFrame by unique values in a specified column.
    
    Parameters:
    df (pd.DataFrame): The input DataFrame.
    column (str): The column name to aggregate by.
    
    Returns:
    pd.DataFrame: A new DataFrame with unique values and their counts.
    """
    if column not in df.columns:
        raise ValueError(f"Column '{column}' does not exist in the DataFrame.")

    if func == 'avg':
        aggregated_df = df.groupby(column).mean().reset_index()
    elif func == 'sum':
        aggregated_df = df.groupby(column).sum().reset_index()
    elif func == 'count':
        aggregated_df = df.groupby(column).size().reset_index(name='count')
    else:
        raise ValueError(f"Unknown aggregation function: {func}")
    return aggregated_df


def create_base_dataframe(frame):
    df_dict = {
        "x": frame.x,
        "y": frame.y,
        "z": frame.z,
        "color": frame.color
    }
    if hasattr(frame, "size") and len(frame.size) > 0:
        df_dict["size"] = frame.size
    df = pd.DataFrame(df_dict)
    
    # Convert to discrete labels in-place
    # Only map if the discrete labels list is not empty (can happen with EMPTY channels)
    if frame.isXDiscrete and len(frame.xDiscreteLabels) > 0:
        df["x"] = df["x"].astype(int).map(lambda idx: frame.xDiscreteLabels[idx] if idx < len(frame.xDiscreteLabels) else str(idx))
    

    if frame.isYDiscrete and len(frame.yDiscreteLabels) > 0:
        df["y"] = df["y"].astype(int).map(lambda idx: frame.yDiscreteLabels[idx] if idx < len(frame.yDiscreteLabels) else str(idx))
        
    
    if frame.isZDiscrete and len(frame.zDiscreteLabels) > 0:
        df["z"] = df["z"].astype(int).map(lambda idx: frame.zDiscreteLabels[idx] if idx < len(frame.zDiscreteLabels) else str(idx))

    if frame.useDiscreteColor and len(frame.labelToColor) > 0:
        df["color"] = df["color"].astype(int).map(lambda idx: frame.labelToColor.get(idx, str(idx)))

    stringify_datetime_columns(df)
    return df


def stringify_datetime_columns(df):
    """Convert any datetime64 columns to ISO strings.

    Pandas serializes datetime64 as raw nanosecond integers by default,
    which downstream renderers display as scientific notation. Converting
    to ISO strings ensures proper date axis auto-detection.
    """
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].dt.strftime("%Y-%m-%d %H:%M:%S")
    return df
