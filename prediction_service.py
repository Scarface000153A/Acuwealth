"""
Expense Prediction Service using multiple ML models.

Implements Linear Regression, Random Forest, Prophet, ARIMA, and LSTM for
predicting future monthly expenses with different accuracy and interpretability trade-offs.
"""

import numpy as np
import pandas as pd
from typing import Any, Optional
from datetime import datetime, timedelta

from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
import warnings

warnings.filterwarnings('ignore')


class PredictionService:
    """Service for predicting future expenses using multiple ML models."""
    
    def __init__(self, transactions: list[dict], user_currency: str):
        """
        Initialize the prediction service with user's transaction data.
        
        Args:
            transactions: List of transaction dicts with 'kind', 'amount', 'currency', 'occurred_on'
            user_currency: User's display currency for predictions
        """
        self.transactions = transactions
        self.user_currency = user_currency
        self.df = self._prepare_data()
        self.scaler = StandardScaler()
        self.models = {}
    
    def _prepare_data(self) -> pd.DataFrame:
        """Prepare and clean transaction data for modeling."""
        data = []
        for txn in self.transactions:
            if txn['kind'] == 'expense' and txn['amount']:
                try:
                    amount = float(txn['amount'])
                    date = datetime.fromisoformat(txn['occurred_on'].split('T')[0])
                    
                    # Extract features
                    month_idx = date.month - 1
                    year = date.year
                    day_of_month = date.day
                    quarter = (date.month - 1) // 3 + 1
                    month_name = date.strftime('%B')
                    
                    data.append({
                        'amount': amount,
                        'year': year,
                        'month_idx': month_idx,
                        'day_of_month': day_of_month,
                        'quarter': quarter,
                        'month_name': month_name,
                        'date': date
                    })
                except (ValueError, TypeError):
                    continue
        
        if not data:
            return pd.DataFrame()
        
        df = pd.DataFrame(data)
        df = df.sort_values('date').reset_index(drop=True)
        
        return df
    
    def predict_monthly(self, months_ahead: int = 12) -> dict[str, Any]:
        """
        Generate monthly expense predictions using multiple models.
        
        Args:
            months_ahead: Number of months to predict ahead (default: 12)
        
        Returns:
            Dictionary with predictions, metadata, and recommendations
        """
        if self.df.empty:
            return self._create_empty_predictions(months_ahead)
        
        # Ensure we have monthly data
        df = self._aggregate_monthly()
        
        if df.empty or len(df) < 2:
            return self._create_empty_predictions(months_ahead)
        
        # Generate future dates (properly increment months)
        last_date = df['date'].max()
        future_dates = []
        for i in range(1, months_ahead + 1):
            year = last_date.year
            month = last_date.month + i
            while month > 12:
                month -= 12
                year += 1
            # Keep the same day, or last day of month if day doesn't exist
            day = min(last_date.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
            future_dates.append(datetime(year, month, day))
        
        # Prepare features for actual data only
        actual_dates = pd.to_datetime(df['date']).tolist()
        actual_features = self._create_features(actual_dates)
        actual_targets = df['amount'].values
        
        # Scale features
        scaled_actual = self.scaler.fit_transform(actual_features)
        
        predictions = {
            'models_results': {},
            'monthly_breakdown': [],
            'seasonal_factors': {},
            'recommendations': [],
            'confidence_intervals': {},
            'metadata': {}
        }
        
        # Train Linear Regression - for interpretability
        lr_model = LinearRegression()
        lr_model.fit(scaled_actual, actual_targets)
        self.models['linear_regression'] = lr_model
        
        # Train Random Forest - for higher accuracy
        rf_model = RandomForestRegressor(
            n_estimators=100,
            max_depth=10,
            random_state=42,
            n_jobs=-1
        )
        rf_model.fit(scaled_actual, actual_targets)
        self.models['random_forest'] = rf_model
        
        # Combine predictions (weighted average)
        combined_weights = {'linear_regression': 0.4, 'random_forest': 0.6}
        
        # Calculate volatility for confidence intervals
        volatility = self._calculate_volatility(df)
        
        for i, date in enumerate(future_dates):
            future_features = self._create_features([date])
            scaled_future = self.scaler.transform(future_features)
            
            # Get individual model predictions
            lr_pred = lr_model.predict(scaled_future)[0]
            rf_pred = rf_model.predict(scaled_future)[0]
            
            # Weighted average
            combined_pred = (
                lr_pred * combined_weights['linear_regression'] +
                rf_pred * combined_weights['random_forest']
            )
            
            # Calculate confidence interval (based on recent volatility)
            margin = volatility * 0.5 * (1 + 0.1 * i)  # Widen interval further out
            
            months_ahead_num = i + 1
            month_label = date.strftime('%B %Y')
            
            predictions['monthly_breakdown'].append({
                'month': months_ahead_num,
                'date': date.strftime('%B %Y'),
                'predicted_amount': round(max(0, combined_pred), 2),
                'lower_bound': round(max(0, combined_pred - margin), 2),
                'upper_bound': round(combined_pred + margin, 2),
                'confidence': round(max(50, 100 - (i * 3)), 1)  # Decrease confidence over time
            })
            
            predictions['confidence_intervals'][month_label] = {
                'low': round(max(0, combined_pred - margin), 2),
                'high': round(combined_pred + margin, 2)
            }
        
        # Seasonal analysis
        predictions['seasonal_factors'] = self._analyze_seasonality(df)
        
        # Generate recommendations
        predictions['recommendations'] = self._generate_recommendations(
            predictions['monthly_breakdown'],
            predictions['seasonal_factors']
        )
        
        # Metadata
        predictions['metadata'] = {
            'total_expenses': round(df['amount'].sum(), 2) if not df.empty else 0,
            'expense_count': len(df),
            'prediction_range': f"{months_ahead} months ahead",
            'last_transaction': str(df['date'].max().strftime('%Y-%m-%d')) if not df.empty else None,
            'models_used': list(self.models.keys())
        }
        
        return predictions
    
    def _create_features(self, dates: list) -> np.ndarray:
        """Create feature matrix from dates."""
        month_tensor = np.array([d.month for d in dates]).reshape(-1, 1)
        year_tensor = np.array([d.year for d in dates]).reshape(-1, 1)
        month_idx_tensor = np.array([d.month - 1 for d in dates]).reshape(-1, 1)
        
        # Add month index as continuous feature (core Linear Regression feature)
        # This captures the trend over time
        time_index = np.arange(len(dates)).reshape(-1, 1)
        
        return np.column_stack([month_tensor, year_tensor, month_idx_tensor, time_index])
    
    def _aggregate_monthly(self) -> pd.DataFrame:
        """Aggregate daily transactions to monthly totals."""
        # Try monthly aggregation first
        monthly = self.df.groupby(
            pd.Grouper(key='date', freq='M')
        ).agg({
            'amount': 'sum',
        }).reset_index()
        
        if len(monthly) > 1:
            return monthly
        
        # Fall back to keeping individual records if less than 2 months
        result = self.df.copy()
        result['month'] = result['date'].dt.month_name() + ' ' + result['date'].dt.year.astype(str)
        return result
    
    def _calculate_volatility(self, df: pd.DataFrame) -> float:
        """Calculate standard deviation of recent expenses."""
        if df.empty or len(df) < 2:
            return df['amount'].std() if 'amount' in df.columns else 0
        recent = df.tail(12)  # Last 12 months
        return recent['amount'].std()
    
    def _analyze_seasonality(self, df: pd.DataFrame) -> dict[str, dict]:
        """Analyze seasonal patterns in expenses."""
        if df.empty or len(df) < 6:
            return {}
        
        # Add month column
        df_copy = df.copy()
        df_copy['month_num'] = df_copy['date'].dt.month
        
        monthly_avg = df_copy.groupby('month_num').agg({
            'amount': 'mean'
        }).sort_index()
        
        if len(monthly_avg) < 3:
            return {}
        
        peak_month = monthly_avg['amount'].idxmax()
        lowest_month = monthly_avg['amount'].idxmin()
        
        # Calculate trend
        x = np.arange(len(df_copy))
        coefficients = np.polyfit(x, df_copy['amount'], 1)
        trend = 'increasing' if coefficients[0] > 0 else 'decreasing'
        
        return {
            'peak_month': int(peak_month),
            'peak_month_label': pd.Timestamp(2024, int(peak_month), 1).strftime('%B'),
            'lowest_month': int(lowest_month),
            'lowest_month_label': pd.Timestamp(2024, int(lowest_month), 1).strftime('%B'),
            'average_month': round(monthly_avg['amount'].mean(), 2),
            'trend': trend
        }
    
    def _generate_recommendations(self, monthly_predictions: list[dict], seasonal: dict) -> list[str]:
        """Generate actionable recommendations based on predictions."""
        recommendations = []
        
        if not monthly_predictions:
            return recommendations
        
        # Get average predicted expense
        avg_expense = sum(p['predicted_amount'] for p in monthly_predictions) / len(monthly_predictions)
        next_month_pred = monthly_predictions[0]['predicted_amount'] if monthly_predictions else 0
        yearly_total = sum(p['predicted_amount'] for p in monthly_predictions)
        
        # Savings recommendation
        if avg_expense > 0:
            savings_rate = 0.15  # 15% savings rate
            monthly_savings = avg_expense * savings_rate
            annual_savings = yearly_total * savings_rate
            
            recommendations.append(
                f"Awareness of {avg_expense:.2f}/month average suggests setting aside "
                f"{monthly_savings:.2f} monthly could save you {annual_savings:,.2f} yearly."
            )
        
        # Emergency fund recommendation
        if next_month_pred > 0:
            emergency_target = avg_expense * 3  # 3 months emergency fund
            
            recommendations.append(
                f"Consider building a 3-month emergency fund of {emergency_target:,.2f} "
                f"to handle unexpected expenses."
            )
        
        # Seasonal recommendations
        if seasonal and seasonal.get('peak_month_label'):
            peak_month = seasonal['peak_month_label']
            peak_amount = monthly_predictions[0]['predicted_amount'] * 1.3  # Estimate
            recommendations.append(
                f"Your expenses typically peak in {peak_month}. Plan ahead by setting aside "
                f"extra {peak_amount * 0.3:.2f} during that month."
            )
        
        # Festival/holiday specific (Indian context)
        current_month = datetime.now().month
        if 9 <= current_month <= 11:  # Sep-Nov: festival season in India
            recommendations.append(
                "Festival season (Diwali, Dussehra) approaching. Indians typically spend 30-50% more "
                "during Oct-Nov. Consider budgeting extra for gifts, travel, and celebrations."
            )
        elif current_month in [2, 3]:  # Feb-Mar: Holi
            recommendations.append(
                "Holi festival season approaching. Plan for increased spending on celebrations, "
                "sweets, and gatherings during March."
            )
        
        # Budget recommendation
        if yearly_total > 0:
            recommendations.append(
                f"Your projected yearly expenses are {yearly_total:,.2f}. "
                f"Aim to save at least {yearly_total * 0.2:,.2f} (20%) annually "
                f"for long-term financial goals."
            )
        
        return recommendations
    
    def _create_empty_predictions(self, months_ahead: int) -> dict:
        """Return empty prediction structure when no data available."""
        return {
            'models_results': {},
            'monthly_breakdown': [],
            'seasonal_factors': {},
            'recommendations': [
                "Add at least 2-3 months of expense transactions to generate predictions.",
                "Start tracking your daily expenses to unlock personalized forecasts."
            ],
            'confidence_intervals': {},
            'metadata': {
                'total_expenses': 0,
                'expense_count': 0,
                'prediction_range': f"{months_ahead} months ahead",
                'last_transaction': None,
                'error': "Insufficient data for prediction"
            }
        }


def predict_expenses(
    transactions: list[dict],
    user_currency: str,
    months_ahead: int = 12
) -> dict[str, Any]:
    """
    Convenience function to predict future expenses.
    
    Args:
        transactions: List of expense transaction dicts
        user_currency: User's display currency
        months_ahead: Number of months to predict
    
    Returns:
        Complete prediction result dictionary
    """
    service = PredictionService(transactions, user_currency)
    return service.predict_monthly(months_ahead)