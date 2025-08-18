#!/usr/bin/env python3
"""
Kalshi Visual Analysis - Create awesome visualizations!
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, date
import re
from typing import Dict, List

def load_analysis_data() -> pd.DataFrame:
    """Load the analysis data"""
    
    print("📊 Loading Kalshi vs Weather analysis data...")
    
    try:
        df = pd.read_csv('kalshi_vs_weather_simple_analysis.csv')
        # Convert date column to datetime
        df['date'] = pd.to_datetime(df['date'])
        print(f"✅ Loaded {len(df)} market records")
        return df
    except FileNotFoundError:
        print("❌ Analysis data not found. Please run the comparison first.")
        return pd.DataFrame()

def create_price_vs_temperature_scatter(df: pd.DataFrame) -> None:
    """Create scatter plot of market prices vs actual temperatures"""
    
    print("📈 Creating price vs temperature scatter plot...")
    
    fig, ax = plt.subplots(figsize=(12, 8))
    
    # Separate winning and losing markets
    won_markets = df[df['market_won']]
    lost_markets = df[~df['market_won']]
    
    # Create scatter plot
    ax.scatter(won_markets['best_temp'], won_markets['kalshi_price'], 
              c='green', alpha=0.7, s=60, label=f'Market Won (n={len(won_markets)})', marker='o')
    ax.scatter(lost_markets['best_temp'], lost_markets['kalshi_price'], 
              c='red', alpha=0.7, s=60, label=f'Market Lost (n={len(lost_markets)})', marker='x')
    
    ax.set_xlabel('Actual Temperature (°F)', fontsize=12, fontweight='bold')
    ax.set_ylabel('Kalshi Market Price (cents)', fontsize=12, fontweight='bold')
    ax.set_title('Kalshi Market Prices vs Actual NYC Temperatures\nJune-August 2025', 
                fontsize=14, fontweight='bold', pad=20)
    
    # Add grid and styling
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=11)
    
    # Add summary statistics as text box
    accuracy = df['prediction_correct'].mean()
    total_markets = len(df)
    temp_range = f"{df['best_temp'].min():.1f}°F - {df['best_temp'].max():.1f}°F"
    
    stats_text = f"""📊 Summary Statistics:
• Total Markets: {total_markets}
• Prediction Accuracy: {accuracy:.1%}
• Temperature Range: {temp_range}
• Avg Temperature: {df['best_temp'].mean():.1f}°F"""
    
    ax.text(0.02, 0.98, stats_text, transform=ax.transAxes, fontsize=10,
            verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
    
    plt.tight_layout()
    filename = 'kalshi_price_vs_temperature_scatter.png'
    plt.savefig(filename, dpi=300, bbox_inches='tight')
    print(f"✅ Saved: {filename}")
    plt.show()

def create_accuracy_by_price_chart(df: pd.DataFrame) -> None:
    """Create accuracy by price range visualization"""
    
    print("🎯 Creating accuracy by price range chart...")
    
    # Define price bins
    price_bins = [0, 0.05, 0.25, 0.50, 0.75, 0.95, 1.0]
    price_labels = ['$0.00-$0.05', '$0.05-$0.25', '$0.25-$0.50', '$0.50-$0.75', '$0.75-$0.95', '$0.95-$1.00']
    
    df['price_bin'] = pd.cut(df['price_pct'], bins=price_bins, labels=price_labels, right=False)
    
    # Calculate accuracy and counts for each bin
    accuracy_by_bin = df.groupby('price_bin').agg({
        'prediction_correct': ['mean', 'count']
    }).round(3)
    
    accuracy_by_bin.columns = ['accuracy', 'count']
    accuracy_by_bin = accuracy_by_bin[accuracy_by_bin['count'] >= 3]  # Only bins with reasonable sample size
    
    if len(accuracy_by_bin) == 0:
        print("❌ Not enough data for price range analysis")
        return
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
    
    # Accuracy chart
    bars1 = ax1.bar(range(len(accuracy_by_bin)), accuracy_by_bin['accuracy'], 
                   color=['darkgreen' if acc > 0.8 else 'orange' if acc > 0.6 else 'red' 
                          for acc in accuracy_by_bin['accuracy']], alpha=0.8)
    
    ax1.set_xlabel('Price Range', fontsize=12, fontweight='bold')
    ax1.set_ylabel('Prediction Accuracy', fontsize=12, fontweight='bold')
    ax1.set_title('Market Accuracy by Price Range', fontsize=14, fontweight='bold')
    ax1.set_xticks(range(len(accuracy_by_bin)))
    ax1.set_xticklabels(accuracy_by_bin.index, rotation=45)
    ax1.set_ylim(0, 1)
    ax1.grid(True, alpha=0.3)
    
    # Add accuracy percentages on bars
    for i, (acc, count) in enumerate(zip(accuracy_by_bin['accuracy'], accuracy_by_bin['count'])):
        ax1.text(i, acc + 0.02, f'{acc:.1%}\n(n={count})', ha='center', va='bottom', 
                fontweight='bold', fontsize=10)
    
    # Sample size chart
    bars2 = ax2.bar(range(len(accuracy_by_bin)), accuracy_by_bin['count'], 
                   color='steelblue', alpha=0.8)
    
    ax2.set_xlabel('Price Range', fontsize=12, fontweight='bold')
    ax2.set_ylabel('Number of Markets', fontsize=12, fontweight='bold')
    ax2.set_title('Market Volume by Price Range', fontsize=14, fontweight='bold')
    ax2.set_xticks(range(len(accuracy_by_bin)))
    ax2.set_xticklabels(accuracy_by_bin.index, rotation=45)
    ax2.grid(True, alpha=0.3)
    
    # Add count labels on bars
    for i, count in enumerate(accuracy_by_bin['count']):
        ax2.text(i, count + max(accuracy_by_bin['count'])*0.01, str(count), 
                ha='center', va='bottom', fontweight='bold', fontsize=11)
    
    plt.tight_layout()
    filename = 'kalshi_accuracy_by_price_range.png'
    plt.savefig(filename, dpi=300, bbox_inches='tight')
    print(f"✅ Saved: {filename}")
    plt.show()

def create_temperature_distribution(df: pd.DataFrame) -> None:
    """Create temperature distribution histogram"""
    
    print("🌡️ Creating temperature distribution chart...")
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
    
    # Temperature histogram
    ax1.hist(df['best_temp'], bins=20, alpha=0.7, color='skyblue', edgecolor='black')
    ax1.axvline(df['best_temp'].mean(), color='red', linestyle='--', linewidth=2, 
               label=f'Mean: {df["best_temp"].mean():.1f}°F')
    ax1.axvline(df['best_temp'].median(), color='orange', linestyle='--', linewidth=2,
               label=f'Median: {df["best_temp"].median():.1f}°F')
    
    ax1.set_xlabel('Temperature (°F)', fontsize=12, fontweight='bold')
    ax1.set_ylabel('Frequency', fontsize=12, fontweight='bold')
    ax1.set_title('Distribution of Actual NYC Temperatures\nJune-August 2025', 
                 fontsize=14, fontweight='bold')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # Market outcomes by temperature
    temp_bins = pd.cut(df['best_temp'], bins=10)
    outcome_by_temp = df.groupby(temp_bins)['market_won'].agg(['sum', 'count']).fillna(0)
    outcome_by_temp['win_rate'] = outcome_by_temp['sum'] / outcome_by_temp['count']
    
    # Only show bins with reasonable sample sizes
    outcome_by_temp = outcome_by_temp[outcome_by_temp['count'] >= 5]
    
    if len(outcome_by_temp) > 0:
        bin_centers = [interval.mid for interval in outcome_by_temp.index]
        ax2.bar(bin_centers, outcome_by_temp['win_rate'], 
               width=2, alpha=0.7, color='green', edgecolor='black')
        
        ax2.set_xlabel('Temperature (°F)', fontsize=12, fontweight='bold')
        ax2.set_ylabel('Market Win Rate', fontsize=12, fontweight='bold')
        ax2.set_title('Market Win Rate by Temperature', fontsize=14, fontweight='bold')
        ax2.grid(True, alpha=0.3)
        ax2.set_ylim(0, max(outcome_by_temp['win_rate']) * 1.1)
    
    plt.tight_layout()
    filename = 'kalshi_temperature_distribution.png'
    plt.savefig(filename, dpi=300, bbox_inches='tight')
    print(f"✅ Saved: {filename}")
    plt.show()

def create_timeline_accuracy(df: pd.DataFrame) -> None:
    """Create timeline of market accuracy"""
    
    print("📅 Creating accuracy timeline...")
    
    # Group by date and calculate daily accuracy
    daily_stats = df.groupby('date').agg({
        'prediction_correct': ['mean', 'count'],
        'best_temp': 'mean',
        'market_won': 'sum'
    }).round(3)
    
    daily_stats.columns = ['accuracy', 'market_count', 'avg_temp', 'markets_won']
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 10), sharex=True)
    
    # Accuracy timeline
    dates = daily_stats.index
    ax1.plot(dates, daily_stats['accuracy'], marker='o', linewidth=2, markersize=6, 
            color='blue', alpha=0.8, label='Daily Accuracy')
    ax1.axhline(df['prediction_correct'].mean(), color='red', linestyle='--', 
               label=f'Overall Average: {df["prediction_correct"].mean():.1%}')
    
    ax1.set_ylabel('Prediction Accuracy', fontsize=12, fontweight='bold')
    ax1.set_title('Kalshi Market Prediction Accuracy Over Time', fontsize=14, fontweight='bold')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    ax1.set_ylim(0, 1)
    
    # Temperature and market activity
    ax2_temp = ax2.twinx()
    
    # Market count bars
    bars = ax2.bar(dates, daily_stats['market_count'], alpha=0.6, color='lightblue', 
                  label='Markets per Day')
    
    # Temperature line
    temp_line = ax2_temp.plot(dates, daily_stats['avg_temp'], color='red', marker='s', 
                             linewidth=2, markersize=4, label='Avg Temperature')
    
    ax2.set_xlabel('Date', fontsize=12, fontweight='bold')
    ax2.set_ylabel('Number of Markets', fontsize=12, fontweight='bold', color='blue')
    ax2_temp.set_ylabel('Temperature (°F)', fontsize=12, fontweight='bold', color='red')
    
    # Rotate x-axis labels
    plt.xticks(rotation=45)
    
    # Combined legend
    lines1, labels1 = ax2.get_legend_handles_labels()
    lines2, labels2 = ax2_temp.get_legend_handles_labels()
    ax2.legend(lines1 + lines2, labels1 + labels2, loc='upper left')
    
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    filename = 'kalshi_accuracy_timeline.png'
    plt.savefig(filename, dpi=300, bbox_inches='tight')
    print(f"✅ Saved: {filename}")
    plt.show()

def create_market_efficiency_analysis(df: pd.DataFrame) -> None:
    """Create market efficiency visualization"""
    
    print("💡 Creating market efficiency analysis...")
    
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
    
    # 1. Price vs Prediction Accuracy
    price_accuracy = df.groupby(pd.cut(df['price_pct'], bins=10))['prediction_correct'].mean()
    price_centers = [interval.mid for interval in price_accuracy.index]
    
    ax1.plot(price_centers, price_accuracy, marker='o', linewidth=3, markersize=8, color='purple')
    ax1.set_xlabel('Market Price', fontsize=11, fontweight='bold')
    ax1.set_ylabel('Prediction Accuracy', fontsize=11, fontweight='bold')
    ax1.set_title('Market Efficiency:\nPrice vs Accuracy Relationship', fontsize=12, fontweight='bold')
    ax1.grid(True, alpha=0.3)
    
    # 2. Market Type Analysis (Range vs Above/Below)
    market_type_stats = df.groupby('temp_type').agg({
        'prediction_correct': ['mean', 'count'],
        'kalshi_price': 'mean'
    }).round(3)
    
    if len(market_type_stats) > 0:
        types = market_type_stats.index
        accuracies = market_type_stats[('prediction_correct', 'mean')]
        
        bars = ax2.bar(types, accuracies, alpha=0.8, 
                      color=['green', 'blue', 'orange'][:len(types)])
        ax2.set_ylabel('Prediction Accuracy', fontsize=11, fontweight='bold')
        ax2.set_title('Accuracy by Market Type', fontsize=12, fontweight='bold')
        ax2.grid(True, alpha=0.3)
        
        # Add labels
        for bar, acc in zip(bars, accuracies):
            ax2.text(bar.get_x() + bar.get_width()/2, acc + 0.01, f'{acc:.1%}', 
                    ha='center', va='bottom', fontweight='bold')
    
    # 3. Overconfidence Analysis
    high_conf_markets = df[df['price_pct'] > 0.9]
    low_conf_markets = df[df['price_pct'] < 0.1]
    
    confidence_data = {
        'High Confidence\n(>90%)': [len(high_conf_markets), high_conf_markets['prediction_correct'].mean()],
        'Low Confidence\n(<10%)': [len(low_conf_markets), low_conf_markets['prediction_correct'].mean()]
    }
    
    conf_names = list(confidence_data.keys())
    conf_counts = [data[0] for data in confidence_data.values()]
    conf_accuracies = [data[1] for data in confidence_data.values()]
    
    bars3 = ax3.bar(conf_names, conf_accuracies, alpha=0.8, color=['darkgreen', 'darkblue'])
    ax3.set_ylabel('Prediction Accuracy', fontsize=11, fontweight='bold')
    ax3.set_title('Market Confidence vs Accuracy', fontsize=12, fontweight='bold')
    ax3.grid(True, alpha=0.3)
    
    # Add labels with counts
    for bar, acc, count in zip(bars3, conf_accuracies, conf_counts):
        ax3.text(bar.get_x() + bar.get_width()/2, acc + 0.01, 
                f'{acc:.1%}\n(n={count})', ha='center', va='bottom', fontweight='bold')
    
    # 4. Temperature Range Prediction Analysis
    temp_ranges = df['temp_high'] - df['temp_low']
    temp_ranges = temp_ranges[temp_ranges.notna()]
    
    if len(temp_ranges) > 0:
        range_accuracy = df[df['temp_type'] == 'range'].groupby(
            pd.cut(df[df['temp_type'] == 'range']['temp_high'] - df[df['temp_type'] == 'range']['temp_low'], 
                   bins=5))['prediction_correct'].mean()
        
        if len(range_accuracy) > 0:
            range_centers = [interval.mid for interval in range_accuracy.index]
            ax4.bar(range_centers, range_accuracy, alpha=0.8, color='coral')
            ax4.set_xlabel('Temperature Range Width (°F)', fontsize=11, fontweight='bold')
            ax4.set_ylabel('Prediction Accuracy', fontsize=11, fontweight='bold')
            ax4.set_title('Accuracy by Range Width', fontsize=12, fontweight='bold')
            ax4.grid(True, alpha=0.3)
    
    plt.tight_layout()
    filename = 'kalshi_market_efficiency_analysis.png'
    plt.savefig(filename, dpi=300, bbox_inches='tight')
    print(f"✅ Saved: {filename}")
    plt.show()

def main():
    """Create all visualizations"""
    
    print("🎨 Creating Kalshi vs NWS Visual Analysis!")
    print("=" * 60)
    
    # Load data
    df = load_analysis_data()
    if df.empty:
        return
    
    print(f"\n📊 Dataset Overview:")
    print(f"  • Total markets: {len(df)}")
    print(f"  • Date range: {df['date'].min().date()} to {df['date'].max().date()}")
    print(f"  • Overall accuracy: {df['prediction_correct'].mean():.1%}")
    print(f"  • Temperature range: {df['best_temp'].min():.1f}°F to {df['best_temp'].max():.1f}°F")
    
    # Create visualizations
    print(f"\n🎯 Creating visualizations...")
    
    try:
        create_price_vs_temperature_scatter(df)
        create_accuracy_by_price_chart(df)
        create_temperature_distribution(df)
        create_timeline_accuracy(df)
        create_market_efficiency_analysis(df)
        
        print(f"\n🎉 All visualizations created successfully!")
        print(f"📁 Generated files:")
        print(f"  • kalshi_price_vs_temperature_scatter.png")
        print(f"  • kalshi_accuracy_by_price_range.png") 
        print(f"  • kalshi_temperature_distribution.png")
        print(f"  • kalshi_accuracy_timeline.png")
        print(f"  • kalshi_market_efficiency_analysis.png")
        
    except Exception as e:
        print(f"❌ Error creating visualizations: {e}")

if __name__ == "__main__":
    main()