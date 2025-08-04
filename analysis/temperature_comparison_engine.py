#!/usr/bin/env python3
"""
Temperature Comparison Engine
Comparative analysis of all weather APIs against Kalshi settlement data
"""

import logging
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from datetime import datetime, date, timedelta
from typing import Dict, List, Tuple
import json
from pathlib import Path

# Import our modular APIs
from modules.nws_api import NWSAPI
from modules.synoptic_api import SynopticAPI
from modules.ncei_asos import NCEIASOS
from modules.kalshi_nws_source import KalshiNWSSource

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('temperature_comparison.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("TempComparison")


class TemperatureComparisonEngine:
    """Engine for comparing temperature data across multiple APIs"""
    
    def __init__(self, station: str = "KNYC"):
        self.station = station
        self.logger = logger
        
        # Initialize all APIs
        self.apis = {
            'kalshi_nws_source': KalshiNWSSource(station),
            'nws_api': NWSAPI(station), 
            'synoptic_api': SynopticAPI(station),
            'ncei_asos': NCEIASOS(station)
        }
        
        self.logger.info(f"Initialized Temperature Comparison Engine for station {station}")
        self.logger.info(f"APIs loaded: {list(self.apis.keys())}")
        
        # Results storage
        self.results = {}
        self.comparison_stats = {}
        
    def collect_data(self, start_date: date, end_date: date) -> Dict:
        """Collect data from all APIs for the specified date range"""
        self.logger.info(f"🔄 Starting data collection from {start_date} to {end_date}")
        
        all_results = {}
        
        for api_name, api_instance in self.apis.items():
            self.logger.info(f"📡 Collecting data from {api_name}...")
            
            try:
                api_results = api_instance.get_date_range_data(start_date, end_date)
                all_results[api_name] = api_results
                
                valid_results = [r for r in api_results if r.get('max_temp') is not None]
                self.logger.info(f"✅ {api_name}: {len(valid_results)}/{len(api_results)} valid results")
                
            except Exception as e:
                self.logger.error(f"❌ Error collecting data from {api_name}: {e}")
                all_results[api_name] = []
        
        self.results = all_results
        return all_results
    
    def create_comparison_dataframe(self) -> pd.DataFrame:
        """Create a unified DataFrame for comparison"""
        self.logger.info("📊 Creating comparison DataFrame...")
        
        all_records = []
        
        for api_name, api_results in self.results.items():
            for result in api_results:
                record = {
                    'date': result['date'],
                    'api': api_name,
                    'max_temp': result.get('max_temp'),
                    'max_time': result.get('max_time'),
                    'count': result.get('count', 0),
                    'station': result.get('station'),
                    'error': result.get('error')
                }
                all_records.append(record)
        
        df = pd.DataFrame(all_records)
        
        # Convert date column
        df['date'] = pd.to_datetime(df['date'])
        
        # Extract hour from max_time for timing analysis
        df['max_hour'] = df['max_time'].apply(
            lambda x: x.hour if pd.notna(x) and hasattr(x, 'hour') else None
        )
        
        self.logger.info(f"📋 Created DataFrame with {len(df)} records across {df['api'].nunique()} APIs")
        return df
    
    def calculate_similarity_metrics(self, df: pd.DataFrame) -> Dict:
        """Calculate similarity metrics compared to Kalshi source"""
        self.logger.info("📈 Calculating similarity metrics...")
        
        # Pivot to get APIs as columns
        temp_pivot = df.pivot_table(
            index='date', 
            columns='api', 
            values='max_temp', 
            aggfunc='first'
        )
        
        if 'kalshi_nws_source' not in temp_pivot.columns:
            self.logger.error("❌ Kalshi NWS source data not available for comparison")
            return {}
        
        kalshi_temps = temp_pivot['kalshi_nws_source'].dropna()
        metrics = {}
        
        for api_name in temp_pivot.columns:
            if api_name == 'kalshi_nws_source':
                continue
                
            api_temps = temp_pivot[api_name].dropna()
            
            # Find common dates
            common_dates = kalshi_temps.index.intersection(api_temps.index)
            if len(common_dates) == 0:
                continue
            
            kalshi_common = kalshi_temps.loc[common_dates]
            api_common = api_temps.loc[common_dates]
            
            # Calculate metrics
            mae = np.mean(np.abs(kalshi_common - api_common))
            rmse = np.sqrt(np.mean((kalshi_common - api_common) ** 2))
            correlation = np.corrcoef(kalshi_common, api_common)[0, 1] if len(common_dates) > 1 else 0
            
            # Percentage of days within 1°F and 2°F
            within_1f = np.mean(np.abs(kalshi_common - api_common) <= 1.0) * 100
            within_2f = np.mean(np.abs(kalshi_common - api_common) <= 2.0) * 100
            
            metrics[api_name] = {
                'mae': mae,
                'rmse': rmse,
                'correlation': correlation,
                'within_1f_percent': within_1f,
                'within_2f_percent': within_2f,
                'common_days': len(common_dates),
                'mean_difference': np.mean(api_common - kalshi_common),
                'std_difference': np.std(api_common - kalshi_common)
            }
            
            self.logger.info(f"📊 {api_name}: MAE={mae:.1f}°F, Correlation={correlation:.3f}, Within 1°F={within_1f:.1f}%")
        
        # Rank APIs by overall similarity (lower MAE + higher correlation)
        rankings = []
        for api_name, stats in metrics.items():
            # Composite score: normalized MAE (lower is better) + correlation (higher is better)
            mae_norm = stats['mae'] / max([m['mae'] for m in metrics.values()])
            corr_score = stats['correlation'] if not np.isnan(stats['correlation']) else 0
            composite_score = corr_score - mae_norm  # Higher is better
            
            rankings.append({
                'api': api_name,
                'composite_score': composite_score,
                'mae': stats['mae'],
                'correlation': stats['correlation'],
                'within_1f_percent': stats['within_1f_percent']
            })
        
        rankings.sort(key=lambda x: x['composite_score'], reverse=True)
        
        self.logger.info("🏆 API Rankings (best to worst similarity to Kalshi):")
        for i, rank in enumerate(rankings, 1):
            self.logger.info(f"  {i}. {rank['api']}: Score={rank['composite_score']:.3f}, MAE={rank['mae']:.1f}°F")
        
        self.comparison_stats = {
            'metrics': metrics,
            'rankings': rankings
        }
        
        return self.comparison_stats
    
    def create_visualizations(self, df: pd.DataFrame):
        """Create comprehensive visualizations"""
        self.logger.info("📊 Creating visualizations...")
        
        # Set style
        plt.style.use('seaborn-v0_8')
        sns.set_palette("husl")
        
        # 1. Temperature comparison over time
        self.plot_temperature_timeline(df)
        
        # 2. API correlation matrix
        self.plot_correlation_matrix(df)
        
        # 3. Difference from Kalshi source
        self.plot_differences_from_kalshi(df)
        
        # 4. Timing analysis
        self.plot_timing_analysis(df)
        
        # 5. Interactive plotly charts
        self.create_interactive_charts(df)
        
        # 6. Summary statistics
        self.plot_summary_statistics()
        
        self.logger.info("✅ All visualizations created")
    
    def plot_temperature_timeline(self, df: pd.DataFrame):
        """Plot temperature comparison timeline"""
        plt.figure(figsize=(15, 8))
        
        # Pivot for plotting
        temp_pivot = df.pivot_table(
            index='date', 
            columns='api', 
            values='max_temp', 
            aggfunc='first'
        )
        
        # Plot each API
        for api in temp_pivot.columns:
            plt.plot(temp_pivot.index, temp_pivot[api], 
                    label=api.replace('_', ' ').title(), 
                    marker='o', markersize=4, alpha=0.8, linewidth=2)
        
        plt.title(f'Daily Maximum Temperature Comparison - {self.station}\n'
                 f'Past 3 Months Comparison Across All APIs', fontsize=16, fontweight='bold')
        plt.xlabel('Date', fontsize=12)
        plt.ylabel('Maximum Temperature (°F)', fontsize=12)
        plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        plt.grid(True, alpha=0.3)
        plt.xticks(rotation=45)
        plt.tight_layout()
        
        plt.savefig('temperature_timeline_comparison.png', dpi=300, bbox_inches='tight')
        plt.show()
        
        self.logger.info("📊 Temperature timeline plot saved")
    
    def plot_correlation_matrix(self, df: pd.DataFrame):
        """Plot correlation matrix between APIs"""
        # Pivot for correlation
        temp_pivot = df.pivot_table(
            index='date', 
            columns='api', 
            values='max_temp', 
            aggfunc='first'
        )
        
        correlation_matrix = temp_pivot.corr()
        
        plt.figure(figsize=(10, 8))
        mask = np.triu(np.ones_like(correlation_matrix, dtype=bool))
        
        sns.heatmap(correlation_matrix, 
                   mask=mask,
                   annot=True, 
                   cmap='RdYlBu_r', 
                   center=0,
                   square=True,
                   fmt='.3f',
                   cbar_kws={"shrink": .8})
        
        plt.title(f'Temperature Data Correlation Matrix - {self.station}', 
                 fontsize=16, fontweight='bold')
        plt.tight_layout()
        
        plt.savefig('temperature_correlation_matrix.png', dpi=300, bbox_inches='tight')
        plt.show()
        
        self.logger.info("📊 Correlation matrix plot saved")
    
    def plot_differences_from_kalshi(self, df: pd.DataFrame):
        """Plot differences from Kalshi source"""
        temp_pivot = df.pivot_table(
            index='date', 
            columns='api', 
            values='max_temp', 
            aggfunc='first'
        )
        
        if 'kalshi_nws_source' not in temp_pivot.columns:
            self.logger.warning("⚠️ No Kalshi source data for difference plot")
            return
        
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))
        fig.suptitle(f'Temperature Differences from Kalshi Settlement Data - {self.station}', 
                    fontsize=16, fontweight='bold')
        
        apis = [col for col in temp_pivot.columns if col != 'kalshi_nws_source']
        
        for i, api in enumerate(apis[:4]):  # Plot up to 4 APIs
            ax = axes[i//2, i%2]
            
            differences = temp_pivot[api] - temp_pivot['kalshi_nws_source']
            differences = differences.dropna()
            
            if len(differences) == 0:
                ax.text(0.5, 0.5, f'No data for {api}', ha='center', va='center', transform=ax.transAxes)
                continue
            
            # Time series of differences
            ax.plot(differences.index, differences, marker='o', alpha=0.7, linewidth=2)
            ax.axhline(y=0, color='red', linestyle='--', alpha=0.5)
            ax.fill_between(differences.index, -1, 1, alpha=0.2, color='green', label='±1°F')
            ax.fill_between(differences.index, -2, 2, alpha=0.1, color='yellow', label='±2°F')
            
            ax.set_title(f'{api.replace("_", " ").title()}\nMAE: {np.mean(np.abs(differences)):.1f}°F')
            ax.set_ylabel('Difference (°F)')
            ax.grid(True, alpha=0.3)
            ax.tick_params(axis='x', rotation=45)
        
        plt.tight_layout()
        plt.savefig('temperature_differences_from_kalshi.png', dpi=300, bbox_inches='tight')
        plt.show()
        
        self.logger.info("📊 Differences from Kalshi plot saved")
    
    def plot_timing_analysis(self, df: pd.DataFrame):
        """Plot analysis of when maximum temperatures occur"""
        # Filter out records without time data
        timing_df = df[df['max_hour'].notna()].copy()
        
        if timing_df.empty:
            self.logger.warning("⚠️ No timing data available for analysis")
            return
        
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))
        fig.suptitle(f'Daily Maximum Temperature Timing Analysis - {self.station}', 
                    fontsize=16, fontweight='bold')
        
        # 1. Hour distribution by API
        ax1 = axes[0, 0]
        for api in timing_df['api'].unique():
            api_data = timing_df[timing_df['api'] == api]
            ax1.hist(api_data['max_hour'], bins=24, alpha=0.6, label=api.replace('_', ' ').title())
        ax1.set_title('Distribution of Peak Temperature Times')
        ax1.set_xlabel('Hour of Day')
        ax1.set_ylabel('Frequency')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # 2. Box plot of timing by API
        ax2 = axes[0, 1]
        timing_pivot = timing_df.pivot_table(index='date', columns='api', values='max_hour')
        timing_pivot.boxplot(ax=ax2)
        ax2.set_title('Peak Temperature Time Distribution by API')
        ax2.set_ylabel('Hour of Day')
        ax2.tick_params(axis='x', rotation=45)
        
        # 3. Timing vs Temperature
        ax3 = axes[1, 0]
        scatter_colors = ['red', 'blue', 'green', 'orange', 'purple']
        for i, api in enumerate(timing_df['api'].unique()):
            api_data = timing_df[timing_df['api'] == api]
            ax3.scatter(api_data['max_hour'], api_data['max_temp'], 
                       alpha=0.6, label=api.replace('_', ' ').title(),
                       color=scatter_colors[i % len(scatter_colors)])
        ax3.set_title('Peak Temperature vs Time of Day')
        ax3.set_xlabel('Hour of Day')
        ax3.set_ylabel('Maximum Temperature (°F)')
        ax3.legend()
        ax3.grid(True, alpha=0.3)
        
        # 4. Average timing by month
        ax4 = axes[1, 1]
        timing_df['month'] = timing_df['date'].dt.month
        monthly_timing = timing_df.groupby(['month', 'api'])['max_hour'].mean().unstack()
        monthly_timing.plot(kind='bar', ax=ax4)
        ax4.set_title('Average Peak Time by Month')
        ax4.set_xlabel('Month')
        ax4.set_ylabel('Average Hour')
        ax4.legend(title='API')
        ax4.tick_params(axis='x', rotation=0)
        
        plt.tight_layout()
        plt.savefig('temperature_timing_analysis.png', dpi=300, bbox_inches='tight')
        plt.show()
        
        self.logger.info("📊 Timing analysis plot saved")
    
    def create_interactive_charts(self, df: pd.DataFrame):
        """Create interactive Plotly charts"""
        # Temperature timeline
        temp_pivot = df.pivot_table(
            index='date', 
            columns='api', 
            values='max_temp', 
            aggfunc='first'
        )
        
        fig = go.Figure()
        
        colors = ['red', 'blue', 'green', 'orange', 'purple']
        for i, api in enumerate(temp_pivot.columns):
            fig.add_trace(go.Scatter(
                x=temp_pivot.index,
                y=temp_pivot[api],
                mode='lines+markers',
                name=api.replace('_', ' ').title(),
                line=dict(color=colors[i % len(colors)]),
                hovertemplate='<b>%{fullData.name}</b><br>Date: %{x}<br>Temp: %{y:.1f}°F<extra></extra>'
            ))
        
        fig.update_layout(
            title=f'Interactive Temperature Comparison - {self.station}',
            xaxis_title='Date',
            yaxis_title='Maximum Temperature (°F)',
            hovermode='x unified',
            template='plotly_white'
        )
        
        fig.write_html('interactive_temperature_comparison.html')
        self.logger.info("📊 Interactive chart saved as HTML")
    
    def plot_summary_statistics(self):
        """Plot summary statistics and rankings"""
        if not self.comparison_stats:
            self.logger.warning("⚠️ No comparison statistics available")
            return
        
        rankings = self.comparison_stats['rankings']
        
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))
        fig.suptitle(f'API Performance Summary - {self.station}', fontsize=16, fontweight='bold')
        
        # 1. Composite scores
        ax1 = axes[0, 0]
        apis = [r['api'] for r in rankings]
        scores = [r['composite_score'] for r in rankings]
        bars1 = ax1.bar(apis, scores, color=['gold', 'silver', '#CD7F32', 'lightblue'][:len(apis)])
        ax1.set_title('Overall Similarity Ranking')
        ax1.set_ylabel('Composite Score')
        ax1.tick_params(axis='x', rotation=45)
        
        # Add value labels
        for bar, score in zip(bars1, scores):
            height = bar.get_height()
            ax1.text(bar.get_x() + bar.get_width()/2., height,
                    f'{score:.3f}', ha='center', va='bottom')
        
        # 2. Mean Absolute Error
        ax2 = axes[0, 1]
        maes = [r['mae'] for r in rankings]
        bars2 = ax2.bar(apis, maes, color='lightcoral')
        ax2.set_title('Mean Absolute Error (Lower is Better)')
        ax2.set_ylabel('MAE (°F)')
        ax2.tick_params(axis='x', rotation=45)
        
        # 3. Correlation
        ax3 = axes[1, 0]
        correlations = [r['correlation'] for r in rankings]
        bars3 = ax3.bar(apis, correlations, color='lightgreen')
        ax3.set_title('Correlation with Kalshi (Higher is Better)')
        ax3.set_ylabel('Correlation Coefficient')
        ax3.tick_params(axis='x', rotation=45)
        
        # 4. Accuracy within 1°F
        ax4 = axes[1, 1]
        within_1f = [r['within_1f_percent'] for r in rankings]
        bars4 = ax4.bar(apis, within_1f, color='lightblue')
        ax4.set_title('Accuracy Within 1°F')
        ax4.set_ylabel('Percentage (%)')
        ax4.tick_params(axis='x', rotation=45)
        
        plt.tight_layout()
        plt.savefig('api_performance_summary.png', dpi=300, bbox_inches='tight')
        plt.show()
        
        self.logger.info("📊 Performance summary plot saved")
    
    def save_results(self):
        """Save all results to files"""
        self.logger.info("💾 Saving results to files...")
        
        # Save raw data
        df = self.create_comparison_dataframe()
        df.to_csv('temperature_comparison_data.csv', index=False)
        
        # Save comparison statistics
        with open('temperature_comparison_stats.json', 'w') as f:
            json.dump(self.comparison_stats, f, indent=2, default=str)
        
        # Save summary report
        with open('temperature_comparison_report.txt', 'w') as f:
            f.write(f"Temperature Comparison Report - {self.station}\n")
            f.write("=" * 50 + "\n\n")
            
            if self.comparison_stats and 'rankings' in self.comparison_stats:
                f.write("API Rankings (Best to Worst Similarity to Kalshi):\n")
                for i, rank in enumerate(self.comparison_stats['rankings'], 1):
                    f.write(f"{i}. {rank['api']}: Score={rank['composite_score']:.3f}, "
                           f"MAE={rank['mae']:.1f}°F, Correlation={rank['correlation']:.3f}\n")
                f.write("\n")
            
            f.write("Files Generated:\n")
            f.write("- temperature_comparison_data.csv: Raw comparison data\n")
            f.write("- temperature_comparison_stats.json: Detailed statistics\n")
            f.write("- temperature_*.png: Visualization plots\n")
            f.write("- interactive_temperature_comparison.html: Interactive chart\n")
        
        self.logger.info("✅ All results saved successfully")
    
    def run_full_analysis(self, months_back: int = 3):
        """Run complete analysis for the specified number of months"""
        self.logger.info(f"🚀 Starting full temperature comparison analysis")
        self.logger.info(f"📅 Analyzing past {months_back} months for station {self.station}")
        
        # Calculate date range
        end_date = date.today() - timedelta(days=1)  # Yesterday
        start_date = end_date - timedelta(days=months_back * 30)
        
        try:
            # 1. Collect data
            self.collect_data(start_date, end_date)
            
            # 2. Create comparison DataFrame
            df = self.create_comparison_dataframe()
            
            # 3. Calculate similarity metrics
            self.calculate_similarity_metrics(df)
            
            # 4. Create visualizations
            self.create_visualizations(df)
            
            # 5. Save results
            self.save_results()
            
            self.logger.info("🎉 Analysis completed successfully!")
            
            # Print summary
            if self.comparison_stats and 'rankings' in self.comparison_stats:
                print("\n" + "="*60)
                print(f"🏆 FINAL RANKINGS - Best APIs for {self.station} Temperature Data")
                print("="*60)
                for i, rank in enumerate(self.comparison_stats['rankings'], 1):
                    print(f"{i}. {rank['api'].replace('_', ' ').title()}")
                    print(f"   Score: {rank['composite_score']:.3f} | MAE: {rank['mae']:.1f}°F | "
                          f"Correlation: {rank['correlation']:.3f} | Within 1°F: {rank['within_1f_percent']:.1f}%")
                print("="*60)
            
        except Exception as e:
            self.logger.error(f"❌ Analysis failed: {e}")
            raise


def main():
    """Main execution function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Temperature API Comparison Engine')
    parser.add_argument('--station', default='KNYC', help='Weather station code (default: KNYC)')
    parser.add_argument('--months', type=int, default=3, help='Number of months to analyze (default: 3)')
    args = parser.parse_args()
    
    # Create and run analysis
    engine = TemperatureComparisonEngine(station=args.station)
    engine.run_full_analysis(months_back=args.months)


if __name__ == "__main__":
    main()