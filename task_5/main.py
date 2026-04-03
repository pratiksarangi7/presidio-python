import pandas as pd
import numpy as np
import os
import joblib
import warnings
from sklearn.model_selection import train_test_split, cross_validate, GridSearchCV
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler, OneHotEncoder, KBinsDiscretizer
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.svm import SVC
from xgboost import XGBClassifier

warnings.filterwarnings('ignore')

def generate_mock_data(n=12453):
    np.random.seed(42)
    data = {
        'user_id': range(1, n + 1),
        'total_spend': np.random.uniform(50, 5000, n),
        'tenure_months': np.random.randint(1, 72, n),
        'last_login_days_ago': np.random.randint(0, 100, n),
        'support_ticket_count': np.random.randint(0, 15, n),
        'contract_type': np.random.choice(['monthly', 'one_year', 'two_year'], n),
        'billing_amount': np.random.uniform(10, 200, n),
        'churn': np.random.choice([0, 1], n, p=[0.75, 0.25])
    }
    df = pd.DataFrame(data)
    
    df.loc[df.sample(frac=0.021).index, 'billing_amount'] = np.nan
    df.loc[df.sample(frac=0.054).index, 'last_login_days_ago'] = np.nan
    return df

def load_and_engineer_features(df):
    print("=== Data Ingestion ===")
    print(f"Loaded {len(df)} records ({len(df.columns)} features)")
    
    missing_billing = df['billing_amount'].isna().mean() * 100
    missing_login = df['last_login_days_ago'].isna().mean() * 100
    
    df['billing_amount'].fillna(df['billing_amount'].median(), inplace=True)
    df['last_login_days_ago'].fillna(df['last_login_days_ago'].median(), inplace=True)
    print(f"Missing values filled: billing_amount ({missing_billing:.1f}%), last_login ({missing_login:.1f}%)")

    df['avg_monthly_spend'] = df['total_spend'] / df['tenure_months'].replace(0, 1)
    df['months_since_last_activity'] = df['last_login_days_ago'] / 30.0
    df['support_freq_ratio'] = df['support_ticket_count'] / df['tenure_months'].replace(0, 1)
    
    X = df.drop(columns=['user_id', 'churn'])
    y = df['churn']
    
    print(f"Engineered 3 new features (avg_monthly_spend, months_since_last_activity, support_freq_ratio...)\n")
    return X, y

def build_preprocessor():
    numeric_features = ['total_spend', 'tenure_months', 'last_login_days_ago', 
                        'support_ticket_count', 'billing_amount', 'avg_monthly_spend', 
                        'months_since_last_activity', 'support_freq_ratio']
    categorical_features = ['contract_type']

    numeric_transformer = Pipeline(steps=[
        ('imputer', SimpleImputer(strategy='median')),
        ('scaler', StandardScaler())
    ])

    categorical_transformer = Pipeline(steps=[
        ('imputer', SimpleImputer(strategy='most_frequent')),
        ('onehot', OneHotEncoder(handle_unknown='ignore', sparse_output=False))
    ])

    binning_transformer = Pipeline(steps=[
        ('imputer', SimpleImputer(strategy='median')),
        ('binner', KBinsDiscretizer(n_bins=5, encode='ordinal', strategy='quantile'))
    ])

    preprocessor = ColumnTransformer(
        transformers=[
            ('num', numeric_transformer, numeric_features),
            ('cat', categorical_transformer, categorical_features),
            ('bin', binning_transformer, ['tenure_months']) 
        ])
    
    return preprocessor

def evaluate_models(X, y, preprocessor):
    models = {
        'Logistic Regression': LogisticRegression(max_iter=1000, random_state=42),
        'Random Forest': RandomForestClassifier(n_estimators=100, random_state=42),
        'XGBoost': XGBClassifier(eval_metric='logloss', random_state=42),
        'SVM (RBF kernel)': SVC(kernel='rbf', random_state=42)
    }

    scoring = ['accuracy', 'precision', 'recall', 'f1']
    results = {}

    print("=== Model Comparison (5-Fold Cross-Validation) ===")
    print(f"+{'-'*25}+{'-'*11}+{'-'*11}+{'-'*10}+{'-'*8}+")
    print(f"| {'Model':<23} | {'Accuracy':<9} | {'Precision':<9} | {'Recall':<8} | {'F1':<6} |")
    print(f"+{'-'*25}+{'-'*11}+{'-'*11}+{'-'*10}+{'-'*8}+")

    for name, model in models.items():
        pipeline = Pipeline(steps=[('preprocessor', preprocessor), ('classifier', model)])
        
        cv_results = cross_validate(pipeline, X, y, cv=5, scoring=scoring, n_jobs=-1)
        
        acc = cv_results['test_accuracy'].mean()
        prec = cv_results['test_precision'].mean()
        rec = cv_results['test_recall'].mean()
        f1 = cv_results['test_f1'].mean()
        
        results[name] = {'Pipeline': pipeline, 'F1': f1}
        
        print(f"| {name:<23} | {acc:<9.3f} | {prec:<9.3f} | {rec:<8.3f} | {f1:<6.3f} |")

    print(f"+{'-'*25}+{'-'*11}+{'-'*11}+{'-'*10}+{'-'*8}+\n")
    
    best_model_name = max(results, key=lambda k: results[k]['F1'])
    return best_model_name

def tune_and_save_best_model(X, y, preprocessor, best_model_name):
    print(f"=== Best Model: {best_model_name} ===")
    
    if best_model_name == 'Logistic Regression':
        model = LogisticRegression(max_iter=1000, random_state=42)
        param_grid = {'classifier__C': [0.1, 1.0, 10.0]}
    elif best_model_name == 'Random Forest':
        model = RandomForestClassifier(random_state=42)
        param_grid = {'classifier__n_estimators': [100, 200], 'classifier__max_depth': [10, 20, None]}
    elif best_model_name == 'XGBoost':
        model = XGBClassifier(eval_metric='logloss', random_state=42)
        param_grid = {'classifier__max_depth': [4, 6], 'classifier__learning_rate': [0.05, 0.1], 'classifier__n_estimators': [100, 350]}
    else: 
        model = SVC(kernel='rbf', random_state=42)
        param_grid = {'classifier__C': [0.1, 1, 10], 'classifier__gamma': ['scale', 'auto']}

    pipeline = Pipeline(steps=[
        ('preprocessor', preprocessor),
        ('classifier', model)
    ])

    grid_search = GridSearchCV(pipeline, param_grid, cv=5, scoring='f1', n_jobs=-1)
    grid_search.fit(X, y)
    
    best_model = grid_search.best_estimator_
    best_params = grid_search.best_params_
    
    formatted_params = {k.replace('classifier__', ''): v for k, v in best_params.items()}
    print(f"Hyperparameters: {formatted_params}\n")

    classifier = best_model.named_steps['classifier']
    
    cat_encoder = best_model.named_steps['preprocessor'].named_transformers_['cat'].named_steps['onehot']
    cat_features = [f"contract_type_{c}" for c in cat_encoder.categories_[0]]
    feature_names = (
        ['total_spend', 'tenure_months', 'last_login_days_ago', 'support_ticket_count', 
         'billing_amount', 'avg_monthly_spend', 'months_since_last_activity', 'support_freq_ratio'] + 
        cat_features + 
        ['tenure_bin']
    )

    if hasattr(classifier, 'feature_importances_'):
        importances = classifier.feature_importances_
    elif hasattr(classifier, 'coef_'):
        importances = np.abs(classifier.coef_[0])
    else:
        importances = np.zeros(len(feature_names))

    if np.any(importances):
        importance_df = pd.DataFrame({'Feature': feature_names, 'Importance': importances})
        importance_df = importance_df.sort_values(by='Importance', ascending=False).head(5)
        
        print("Top 5 Feature Importances:")
        for i, (idx, row) in enumerate(importance_df.iterrows(), 1):
            print(f"{i}. {row['Feature']:<30} — {row['Importance']:.3f}")
    else:
        print("Top 5 Feature Importances:\n(Not natively available for SVM RBF kernel)")
    
    os.makedirs('models', exist_ok=True)
    safe_name = best_model_name.replace(' ', '_').replace('(', '').replace(')', '').lower()
    model_path = f'models/churn_{safe_name}_v2.pkl'
    joblib.dump(best_model, model_path)
    print(f"\nModel saved to {model_path}")

if __name__ == "__main__":
    raw_df = generate_mock_data(12453)
    X, y = load_and_engineer_features(raw_df)
    preprocessor = build_preprocessor()
    
    best_model_name = evaluate_models(X, y, preprocessor)
    
    tune_and_save_best_model(X, y, preprocessor, best_model_name)