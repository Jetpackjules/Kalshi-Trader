#!/usr/bin/env python3
"""
Simplified Temperature Comparison using Kalshi betting results as ground truth
"""

import logging
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, date, timedelta
import re
import os
import sys

# Add root directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import our modular APIs - paths relative to root
from modules.nws_api import NWSAPI
from modules.synoptic_api import SynopticAPI
from modules.ncei_asos import NCEIASOS

# ===============================================
# CONFIGURATION PARAMETERS
# ===============================================
ANALYSIS_DAYS_BACK = 7  # Number of days back to analyze (7 days including Aug 3rd)
STATION = "KNYC"  # Weather station code
OUTPUT_BASE_DIR = "analysis/outputs"
START_DATE = date(2025, 7, 31)  # Start from July 31st backwards (where we have ASOS data)
GROUND_TRUTH_SOURCE = "ASOS_5MIN"  # Use ASOS 5-minute data as ground truth

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("SimpleComparison")


def load_asos_ground_truth():
    """Load ASOS 5-minute data as ground truth temperature data"""
    logger.info("📊 Loading ASOS 5-minute data as ground truth...")
    
    # Create ASOS instance to get ground truth data
    asos_api = NCEIASOS(STATION)
    
    # Generate date range from START_DATE backwards
    end_date = START_DATE
    start_date = START_DATE - timedelta(days=ANALYSIS_DAYS_BACK - 1)
    
    ground_truth_data = []
    
    # Get ASOS data for each day
    current_date = start_date
    while current_date <= end_date:
        try:
            result = asos_api.get_daily_max_temperature(current_date)
            if result.get('max_temp'):
                ground_truth_data.append({
                    'date': current_date,
                    'asos_temp': result['max_temp'],
                    'asos_time': result.get('max_time'),
                    'asos_count': result.get('count', 0)
                })
                logger.info(f"✅ ASOS ground truth {current_date}: {result['max_temp']}°F")
            else:
                logger.warning(f"⚠️ No ASOS data for {current_date}")
        except Exception as e:
            logger.error(f"❌ Error getting ASOS data for {current_date}: {e}")
        
        current_date += timedelta(days=1)
    
    ground_truth = pd.DataFrame(ground_truth_data)
    
    logger.info(f"✅ Loaded {len(ground_truth)} days of ASOS ground truth data")
    if len(ground_truth) > 0:
        logger.info(f"📅 Date range: {ground_truth['date'].min()} to {ground_truth['date'].max()}")
    
    return ground_truth


def collect_api_data(ground_truth_dates, station="KNYC"):
    """Collect data from ALL APIs for the ground truth dates"""
    logger.info(f"🔄 Collecting API data for {len(ground_truth_dates)} dates...")
    
    apis = {
        'nws_api': NWSAPI(station),
        'synoptic_api': SynopticAPI(station),
        'ncei_asos': NCEIASOS(station)  # This will be our ground truth comparison
    }
    
    all_results = []
    
    for api_name, api_instance in apis.items():
        logger.info(f"📡 Collecting data from {api_name}...")
        
        for target_date in ground_truth_dates:
            try:
                result = api_instance.get_daily_max_temperature(target_date)
                all_results.append({
                    'date': target_date,
                    'api': api_name,
                    'max_temp': result.get('max_temp'),
                    'max_time': result.get('max_time'),
                    'count': result.get('count', 0)
                })
                
                if result.get('max_temp'):
                    logger.debug(f"  {target_date}: {result['max_temp']}°F")
                    
            except Exception as e:
                logger.error(f"  Error getting {api_name} data for {target_date}: {e}")
                all_results.append({
                    'date': target_date,
                    'api': api_name,
                    'max_temp': None,
                    'max_time': None,
                    'count': 0
                })
    
    return pd.DataFrame(all_results)


def create_comparison_analysis(ground_truth, api_data):
    """Create comprehensive comparison analysis using ASOS as ground truth"""
    logger.info("📊 Creating comparison analysis...")
    
    # Merge with ASOS ground truth
    comparison_df = api_data.merge(ground_truth, on='date', how='inner')
    
    # Calculate differences for each API compared to ASOS ground truth
    comparison_df['temp_diff'] = comparison_df['max_temp'] - comparison_df['asos_temp']
    comparison_df['abs_diff'] = comparison_df['temp_diff'].abs()
    
    # Filter valid data
    valid_data = comparison_df[comparison_df['max_temp'].notna()].copy()
    
    logger.info(f"📈 Analysis based on {len(valid_data)} valid data points")
    
    # Calculate metrics by API
    metrics = {}
    for api in valid_data['api'].unique():
        api_data_subset = valid_data[valid_data['api'] == api]
        
        if len(api_data_subset) == 0:
            continue
            
        mae = api_data_subset['abs_diff'].mean()
        rmse = np.sqrt((api_data_subset['temp_diff'] ** 2).mean())
        correlation = np.corrcoef(api_data_subset['max_temp'], api_data_subset['asos_temp'])[0, 1]
        
        within_1f = (api_data_subset['abs_diff'] <= 1.0).mean() * 100
        within_2f = (api_data_subset['abs_diff'] <= 2.0).mean() * 100
        
        metrics[api] = {
            'mae': mae,
            'rmse': rmse,
            'correlation': correlation,
            'within_1f_percent': within_1f,
            'within_2f_percent': within_2f,
            'data_points': len(api_data_subset),
            'mean_bias': api_data_subset['temp_diff'].mean()
        }
        
        logger.info(f"📊 {api}: MAE={mae:.1f}°F, RMSE={rmse:.1f}°F, Corr={correlation:.3f}, Within1°F={within_1f:.1f}%")
    
    # Rank APIs
    rankings = []
    for api, stats in metrics.items():
        # Composite score: higher correlation, lower MAE
        mae_norm = stats['mae'] / max([m['mae'] for m in metrics.values()])
        corr_score = stats['correlation'] if not np.isnan(stats['correlation']) else 0
        composite_score = corr_score - mae_norm
        
        rankings.append({
            'api': api,
            'rank': 0,  # Will be filled
            'composite_score': composite_score,
            'mae': stats['mae'],
            'rmse': stats['rmse'],
            'correlation': stats['correlation'],
            'within_1f_percent': stats['within_1f_percent'],
            'data_points': stats['data_points']
        })
    
    rankings.sort(key=lambda x: x['composite_score'], reverse=True)
    for i, rank in enumerate(rankings):
        rank['rank'] = i + 1
    
    logger.info("🏆 Final API Rankings:")
    for rank in rankings:
        logger.info(f"  {rank['rank']}. {rank['api']}: Score={rank['composite_score']:.3f}, MAE={rank['mae']:.1f}°F")
    
    return valid_data, metrics, rankings


def create_visualizations(comparison_data, metrics, rankings):
    """Create visualizations"""
    logger.info("📊 Creating visualizations...")
    
    import matplotlib
    matplotlib.use('Agg')  # Use non-interactive backend
    plt.style.use('seaborn-v0_8')
    fig, axes = plt.subplots(2, 3, figsize=(18, 12))
    fig.suptitle('NYC Temperature API Comparison vs ASOS 5-Minute Ground Truth', fontsize=16, fontweight='bold')
    
    # 1. Temperature scatter plots
    ax1 = axes[0, 0]
    colors = ['red', 'blue', 'green']
    for i, api in enumerate(comparison_data['api'].unique()):
        api_data = comparison_data[comparison_data['api'] == api]
        ax1.scatter(api_data['asos_temp'], api_data['max_temp'], 
                   alpha=0.7, label=api.replace('_', ' ').title(), 
                   color=colors[i % len(colors)])
    
    # Perfect correlation line
    min_temp = min(comparison_data['asos_temp'].min(), comparison_data['max_temp'].min())
    max_temp = max(comparison_data['asos_temp'].max(), comparison_data['max_temp'].max())
    ax1.plot([min_temp, max_temp], [min_temp, max_temp], 'k--', alpha=0.5, label='Perfect Match')
    
    ax1.set_xlabel('ASOS Ground Truth Temperature (°F)')
    ax1.set_ylabel('API Temperature (°F)')
    ax1.set_title('Temperature Correlation')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # 2. Difference distributions
    ax2 = axes[0, 1]
    for api in comparison_data['api'].unique():
        api_data = comparison_data[comparison_data['api'] == api]
        ax2.hist(api_data['temp_diff'], bins=20, alpha=0.6, label=api.replace('_', ' ').title())
    ax2.axvline(x=0, color='red', linestyle='--', alpha=0.7)
    ax2.set_xlabel('Temperature Difference (API - ASOS) °F')
    ax2.set_ylabel('Frequency')
    ax2.set_title('Temperature Difference Distribution')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    # 3. Time series comparison
    ax3 = axes[0, 2]
    pivot_data = comparison_data.pivot_table(index='date', columns='api', values='max_temp')
    ground_truth_series = comparison_data.drop_duplicates('date').set_index('date')['asos_temp']
    
    ax3.plot(ground_truth_series.index, ground_truth_series.values, 
             'k-', linewidth=3, label='ASOS (Ground Truth)', alpha=0.8)
    
    for i, api in enumerate(pivot_data.columns):
        ax3.plot(pivot_data.index, pivot_data[api], 
                marker='o', alpha=0.7, label=api.replace('_', ' ').title())
    
    ax3.set_xlabel('Date')
    ax3.set_ylabel('Temperature (°F)')
    ax3.set_title('Temperature Time Series')
    ax3.legend()
    ax3.grid(True, alpha=0.3)
    plt.setp(ax3.xaxis.get_majorticklabels(), rotation=45)
    
    # 4. Performance metrics
    ax4 = axes[1, 0]
    apis = [r['api'] for r in rankings]
    maes = [r['mae'] for r in rankings]
    colors_bar = ['gold', 'silver', '#CD7F32'][:len(apis)] + ['lightblue'] * (len(apis) - 3)
    
    bars = ax4.bar(apis, maes, color=colors_bar)
    ax4.set_ylabel('Mean Absolute Error (°F)')
    ax4.set_title('API Accuracy (Lower is Better)')
    ax4.tick_params(axis='x', rotation=45)
    
    # Add value labels
    for bar, mae in zip(bars, maes):
        height = bar.get_height()
        ax4.text(bar.get_x() + bar.get_width()/2., height,
                f'{mae:.1f}', ha='center', va='bottom')
    
    # 5. Correlation coefficients
    ax5 = axes[1, 1]
    correlations = [r['correlation'] for r in rankings]
    ax5.bar(apis, correlations, color=colors_bar)
    ax5.set_ylabel('Correlation Coefficient')
    ax5.set_title('API Correlation (Higher is Better)')
    ax5.tick_params(axis='x', rotation=45)
    ax5.set_ylim(0, 1)
    
    # 6. Accuracy within thresholds
    ax6 = axes[1, 2]
    within_1f = [r['within_1f_percent'] for r in rankings]
    # Get within_2f from metrics since rankings doesn't have it
    within_2f = []
    for r in rankings:
        api_name = r['api']
        if api_name in metrics:
            within_2f.append(metrics[api_name]['within_2f_percent'])
        else:
            within_2f.append(0)
    
    x = np.arange(len(apis))
    width = 0.35
    
    ax6.bar(x - width/2, within_1f, width, label='Within 1°F', color='lightgreen')
    ax6.bar(x + width/2, within_2f, width, label='Within 2°F', color='lightblue')
    
    ax6.set_ylabel('Percentage (%)')
    ax6.set_title('API Accuracy Thresholds')
    ax6.set_xticks(x)
    ax6.set_xticklabels(apis, rotation=45)
    ax6.legend()
    ax6.set_ylim(0, 100)
    
    plt.tight_layout()
    os.makedirs(f'{OUTPUT_BASE_DIR}/visualizations', exist_ok=True)
    plt.savefig(f'{OUTPUT_BASE_DIR}/visualizations/nyc_temperature_api_comparison.png', dpi=300, bbox_inches='tight')
    # plt.show()  # Skip showing plots to avoid timeout
    
    logger.info("📊 Visualizations saved as nyc_temperature_api_comparison.png")


def create_timing_analysis(comparison_data):
    """Analyze timing of maximum temperatures"""
    logger.info("🕐 Creating timing analysis...")
    
    timing_data = comparison_data[comparison_data['max_time'].notna()].copy()
    if timing_data.empty:
        logger.warning("⚠️ No timing data available")
        return
    
    # Extract hour
    timing_data['max_hour'] = timing_data['max_time'].apply(
        lambda x: x.hour if hasattr(x, 'hour') else None
    )
    timing_data = timing_data[timing_data['max_hour'].notna()]
    
    plt.figure(figsize=(12, 8))
    
    # Create subplots for timing analysis
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    fig.suptitle('Daily Maximum Temperature Timing Analysis', fontsize=16, fontweight='bold')
    
    # 1. Hour distribution by API
    ax1 = axes[0, 0]
    for api in timing_data['api'].unique():
        api_timing = timing_data[timing_data['api'] == api]
        ax1.hist(api_timing['max_hour'], bins=24, alpha=0.6, 
                label=api.replace('_', ' ').title(), density=True)
    ax1.set_xlabel('Hour of Day')
    ax1.set_ylabel('Density')
    ax1.set_title('Peak Temperature Time Distribution')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # 2. Box plot by API
    ax2 = axes[0, 1]
    timing_pivot = timing_data.pivot_table(index='date', columns='api', values='max_hour')
    timing_pivot.boxplot(ax=ax2)
    ax2.set_ylabel('Hour of Day')
    ax2.set_title('Peak Time Distribution by API')
    ax2.tick_params(axis='x', rotation=45)
    
    # 3. Temperature vs timing
    ax3 = axes[1, 0]
    for i, api in enumerate(timing_data['api'].unique()):
        api_timing = timing_data[timing_data['api'] == api]
        ax3.scatter(api_timing['max_hour'], api_timing['max_temp'], 
                   alpha=0.6, label=api.replace('_', ' ').title())
    ax3.set_xlabel('Hour of Day')
    ax3.set_ylabel('Maximum Temperature (°F)')
    ax3.set_title('Temperature vs Time of Peak')
    ax3.legend()
    ax3.grid(True, alpha=0.3)
    
    # 4. Average timing statistics
    ax4 = axes[1, 1]
    timing_stats = timing_data.groupby('api')['max_hour'].agg(['mean', 'std']).reset_index()
    
    x = np.arange(len(timing_stats))
    ax4.bar(x, timing_stats['mean'], yerr=timing_stats['std'], 
           capsize=5, alpha=0.7, color=['red', 'blue', 'green'][:len(timing_stats)])
    ax4.set_ylabel('Average Hour of Day')
    ax4.set_title('Average Peak Time by API')
    ax4.set_xticks(x)
    ax4.set_xticklabels([api.replace('_', ' ').title() for api in timing_stats['api']])
    ax4.grid(True, alpha=0.3)
    
    plt.tight_layout()
    os.makedirs(f'{OUTPUT_BASE_DIR}/visualizations', exist_ok=True)
    plt.savefig(f'{OUTPUT_BASE_DIR}/visualizations/nyc_temperature_timing_analysis.png', dpi=300, bbox_inches='tight')
    # plt.show()  # Skip showing plots to avoid timeout
    
    logger.info("📊 Timing analysis saved as nyc_temperature_timing_analysis.png")


def main():
    """Main execution"""
    logger.info("🚀 Starting simplified temperature comparison analysis")
    
    # 1. Load ASOS ground truth
    ground_truth = load_asos_ground_truth()
    
    # 2. Get list of dates from ground truth
    available_dates = ground_truth['date'].tolist()
    
    logger.info(f"📅 Analyzing {len(available_dates)} dates")
    logger.info(f"📅 Configuration: {ANALYSIS_DAYS_BACK} days back from {START_DATE}, Station: {STATION}")
    logger.info(f"📅 Ground Truth Source: {GROUND_TRUTH_SOURCE}")
    
    # 3. Collect API data
    api_data = collect_api_data(available_dates, station=STATION)
    
    # 4. Create comparison analysis
    comparison_data, metrics, rankings = create_comparison_analysis(ground_truth, api_data)
    
    # 5. Create visualizations
    create_visualizations(comparison_data, metrics, rankings)
    
    # 6. Create timing analysis
    create_timing_analysis(comparison_data)
    
    # 7. Save results
    os.makedirs(f'{OUTPUT_BASE_DIR}/data', exist_ok=True)
    os.makedirs(f'{OUTPUT_BASE_DIR}/reports', exist_ok=True)
    
    comparison_data.to_csv(f'{OUTPUT_BASE_DIR}/data/temperature_api_comparison_results.csv', index=False)
    
    # Create summary report
    with open(f'{OUTPUT_BASE_DIR}/reports/temperature_comparison_summary.txt', 'w') as f:
        f.write("NYC Temperature API Comparison Summary\n")
        f.write("="*50 + "\n\n")
        f.write("Final Rankings (Best to Worst):\n")
        for rank in rankings:
            f.write(f"{rank['rank']}. {rank['api'].replace('_', ' ').title()}\n")
            f.write(f"   MAE: {rank['mae']:.1f}°F\n")
            f.write(f"   RMSE: {rank['rmse']:.1f}°F\n")
            f.write(f"   Correlation: {rank['correlation']:.3f}\n")
            f.write(f"   Within 1°F: {rank['within_1f_percent']:.1f}%\n")
            f.write(f"   Data Points: {rank['data_points']}\n\n")
    
    logger.info("🎉 Analysis completed successfully!")
    
    # Print final rankings
    print("\n" + "="*60)
    print("🏆 FINAL RANKINGS - Best APIs for NYC Temperature Data")
    print("="*60)
    for rank in rankings:
        print(f"{rank['rank']}. {rank['api'].replace('_', ' ').title()}")
        print(f"   Score: {rank['composite_score']:.3f} | MAE: {rank['mae']:.1f}°F | "
              f"Correlation: {rank['correlation']:.3f} | Within 1°F: {rank['within_1f_percent']:.1f}%")
    print("="*60)


if __name__ == "__main__":
    main()