"""
Data formatting utilities for UI display
"""

import pandas as pd
from pathlib import Path
from io import StringIO


def parse_split_csv(file_path: Path) -> tuple:
    """Parse CSV file split by Development and Maintenance sections
    
    Returns:
        tuple: (dev_df, maint_df, metadata_dict)
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    dev_lines = []
    maint_lines = []
    current_section = None
    metadata = {}
    
    for line in lines:
        stripped = line.strip()
        
        # Parse metadata lines
        if stripped.startswith('Generated:'):
            metadata['generated'] = stripped.replace('Generated:', '').strip()
            continue
        
        if stripped == 'DEVELOPMENT':
            current_section = 'dev'
            continue
        elif stripped == 'MAINTENANCE':
            current_section = 'maint'
            continue
        elif not stripped:
            continue
        
        if current_section == 'dev':
            dev_lines.append(line)
        elif current_section == 'maint':
            maint_lines.append(line)
    
    # Parse into DataFrames
    dev_df = pd.read_csv(StringIO(''.join(dev_lines))) if dev_lines else pd.DataFrame()
    maint_df = pd.read_csv(StringIO(''.join(maint_lines))) if maint_lines else pd.DataFrame()
    
    return dev_df, maint_df, metadata


def calculate_summary_stats(dev_df: pd.DataFrame, maint_df: pd.DataFrame) -> dict:
    """Calculate summary statistics from both Development and Maintenance DataFrames"""
    
    def get_stats_from_df(df):
        if df.empty:
            return 0, 0, 0
        data_df = df[df['Project'].notna() & (df['Project'] != 'TOTAL')]
        projects = data_df['Project'].nunique() if 'Project' in data_df.columns else 0
        components = data_df['Component'].nunique() if 'Component' in data_df.columns else 0
        
        # Get total hours from TOTAL row
        total_row = df[df['Project'] == 'TOTAL']
        if not total_row.empty:
            numeric_cols = total_row.select_dtypes(include=['float64', 'int64']).columns
            hours = total_row[numeric_cols].sum().sum()
        else:
            numeric_cols = data_df.select_dtypes(include=['float64', 'int64']).columns
            hours = data_df[numeric_cols].sum().sum()
        
        return projects, components, hours
    
    dev_projects, dev_components, dev_hours = get_stats_from_df(dev_df)
    maint_projects, maint_components, maint_hours = get_stats_from_df(maint_df)
    
    # Team members count - for quarterly reports, divide by 4 (Q1-Q4 per member)
    team_members = 0
    if not dev_df.empty:
        # Check if this is a quarterly report (columns end with Q1, Q2, Q3, Q4)
        cols = [c for c in dev_df.columns if c not in ['Project', 'Component']]
        if cols and any('Q' in str(col) for col in cols):
            # Quarterly report: each member has 4 columns (Q1-Q4)
            team_members = len(cols) // 4
        else:
            # Yearly report: one column per member
            team_members = len(cols)
    elif not maint_df.empty:
        cols = [c for c in maint_df.columns if c not in ['Project', 'Component']]
        if cols and any('Q' in str(col) for col in cols):
            team_members = len(cols) // 4
        else:
            team_members = len(cols)
    
    return {
        'projects': max(dev_projects, maint_projects),
        'components': dev_components + maint_components,
        'team_members': team_members,
        'dev_hours': dev_hours,
        'maint_hours': maint_hours,
        'total_hours': dev_hours + maint_hours
    }


def transform_to_multiindex(df: pd.DataFrame) -> pd.DataFrame:
    """Transform quarterly columns to multi-level index for better display"""
    if df.empty:
        return df
    
    # Check if this is a quarterly report
    cols = [c for c in df.columns if c not in ['Project', 'Component']]
    if not cols or not any('Q' in str(col) for col in cols):
        return df  # Not quarterly, return as-is
    
    # Create multi-level columns
    new_columns = [('', 'Project'), ('', 'Component')]
    
    for col in cols:
        # Parse "Name Q1" format
        if ' Q' in col:
            parts = col.rsplit(' Q', 1)
            name = parts[0]
            quarter = f'Q{parts[1]}'
            new_columns.append((name, quarter))
        else:
            new_columns.append(('', col))
    
    # Create new dataframe with multi-level columns
    df_multi = df.copy()
    df_multi.columns = pd.MultiIndex.from_tuples(new_columns)
    
    return df_multi
