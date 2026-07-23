from libs.common.audit_html import AuditDashboardGenerator

"""
Optimized Anaplan History Audit Script with Performance Enhancements
- Chunked data processing for large files
- Parallel processing with process pools
- Memory-optimized pandas operations

全ての設定は config.py で管理されます。
"""
import logging
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
from anaplan_sdk import Client

# 設定ファイルのインポート
try:
    from config import (
        ANAPLAN_PASSWORD,
        ANAPLAN_USER_EMAIL,
        LOG_LEVEL,
        MAX_WORKERS,
        MODELS,
        OUTPUT_FOLDER,
        TIMEOUT,
        ModelConfig,
    )
except ImportError:
    print("エラー: config.py が見つかりません。")
    print("config.example.py を config.py にコピーして設定を行ってください。")
    exit(1)


# Setup logging
today = datetime.now(UTC).strftime("%Y%m%d")
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
from libs.common.logging_setup import setup_logging

logger = setup_logging(f"{OUTPUT_FOLDER}/{today}.log", level=LOG_LEVEL, logger_name=__name__)


def get_logger():
    """Get logger for multiprocessing contexts"""
    return logging.getLogger(__name__)


class OptimizedAnaplanExporter:
    """Optimized Anaplan export handler with chunked processing"""

    def __init__(self):
        self.logger = get_logger()

    def create_client(self, ws_id: str, m_id: str) -> Client:
        """Create and return an Anaplan SDK client"""
        from libs.common.anaplan_sdk_client import create_anaplan_client
        return create_anaplan_client(
            workspace_id=ws_id,
            model_id=m_id,
            user_email=ANAPLAN_USER_EMAIL,
            password=ANAPLAN_PASSWORD,
            timeout=TIMEOUT
        )

    def export_data(self, model: ModelConfig) -> dict | None:
        """Export data from Anaplan for a given model"""
        try:
            os.makedirs(OUTPUT_FOLDER, exist_ok=True)
            start_time = datetime.now(UTC)

            # Create client and export
            client = self.create_client(model.ws_id, model.m_id)
            self.logger.info(f"{model.model_name}: Starting export")

            timestamp = datetime.now(UTC).strftime('%Y%m%d%H%M')
            file_name = f"{timestamp}{model.file_suffix}"
            export_file_path = Path(OUTPUT_FOLDER) / f"{file_name}.tsv"

            # Export data
            export_data = client.export_and_download(action_id=int(model.action_id))

            with open(export_file_path, "wb") as f:
                f.write(export_data)

            export_time = (datetime.now(UTC) - start_time).total_seconds()
            self.logger.info(f"{model.model_name}: Export completed in {export_time:.2f}s")

            # Process data with chunking
            result = self._process_export_chunked(export_file_path, model, file_name)

            process_time = (datetime.now(UTC) - start_time).total_seconds()
            self.logger.info(f"{model.model_name}: Total time {process_time:.2f}s")

            return result

        except Exception as e:
            self.logger.error(f"{model.model_name}: Error - {str(e)}", exc_info=True)
            # Return error information instead of None
            return {
                'status': 'error',
                'model_name': model.model_name,
                'error': str(e),
                'error_type': type(e).__name__
            }

    def _process_export_chunked(
        self,
        export_file_path: Path,
        model: ModelConfig,
        file_name: str
    ) -> dict | None:
        """Process exported data using chunked reading for memory efficiency"""
        try:
            # Define optimal dtypes to reduce memory usage

            total_rows = 0

            # Read file in chunks
            # Use Polars lazy scanning
            lazy_df = pl.scan_csv(
                export_file_path,
                separator="\t",
                infer_schema_length=10000,
                ignore_errors=True
            )

            # Check required columns (by collecting just 1 row)
            head_df = lazy_df.head(1).collect()
            if "User" not in head_df.columns:
                self.logger.error(f"{model.model_name}: 'User' column not found")
                return None

            # Get row count
            total_rows = lazy_df.select(pl.len()).collect().item()
            self.logger.info(f"{model.model_name}: Processed {total_rows:,} total rows")

            # Count users
            user_count_df = lazy_df.group_by("User").agg(pl.len().alias("ID")).collect()

            if len(user_count_df) == 0:
                self.logger.warning(f"{model.model_name}: No data found")
                return None


            # Merge with user details
            result_df = self._merge_user_details(user_count_df, model)
            result_df = result_df.with_columns(pl.lit(model.model_name).alias('Model'))

            # Save summary
            summary_path = Path(OUTPUT_FOLDER) / f"{file_name}_summary.csv"
            result_df.with_columns(pl.col('User').cast(pl.String)).write_csv(summary_path)

            self.logger.info(f"{model.model_name}: Summary saved")

            return {
                'status': 'success',
                'dataframe': result_df,
                'total_rows': total_rows,
                'unique_users': len(user_count_df),
                'model_name': model.model_name
            }

        except Exception as e:
            self.logger.error(f"{model.model_name}: Processing error - {str(e)}")
            return None

    def _merge_user_details(
        self,
        user_count: pl.DataFrame,
        model: ModelConfig
    ) -> pl.DataFrame:
        """Merge user activity counts with user details"""
        users_csv_path = Path(OUTPUT_FOLDER) / model.users_csv

        if users_csv_path.exists():
            try:
                # Read specific columns
                users = pl.read_csv(users_csv_path, ignore_errors=True)

                # Check for "Unnamed: 0" or use first column
                user_col = "Unnamed: 0" if "Unnamed: 0" in users.columns else users.columns[0]
                users = users.rename({user_col: "User"})

                # Keep only necessary columns if they exist
                keep_cols = ["User"]
                for col in ["First Name", "Last Name", "Model Role"]:
                    if col in users.columns:
                        keep_cols.append(col)

                users = users.select(keep_cols)

                return user_count.join(
                    users,
                    on="User",
                    how="left"
                )
            except Exception as e:
                self.logger.warning(f"{model.model_name}: Error loading users CSV: {e}")

        # Fallback if users CSV not found or error
        return user_count.with_columns(
            pl.lit("N/A").alias("First Name"),
            pl.lit("N/A").alias("Last Name"),
            pl.lit("N/A").alias("Model Role")
        )




def process_model(model: ModelConfig) -> dict | None:
    """Wrapper for parallel processing"""
    exporter = OptimizedAnaplanExporter()
    return exporter.export_data(model)


def main():
    """Main execution with parallel processing"""
    try:
        start_time = datetime.now(UTC)
        logger.info(f"Starting audit for {len(MODELS)} model(s) with {MAX_WORKERS} workers")

        # Parallel processing with ProcessPoolExecutor
        results = []
        failed_models = []
        with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_model = {executor.submit(process_model, model): model for model in MODELS}

            for future in as_completed(future_to_model):
                model = future_to_model[future]
                try:
                    result = future.result()
                    if result:
                        if result.get('status') == 'error':
                            # Failed model
                            failed_models.append(result)
                            logger.error(f"{model.model_name}: Failed - {result['error']}")
                        else:
                            # Success model
                            results.append(result)
                            logger.info(
                                f"{model.model_name}: Completed - "
                                f"{result['total_rows']:,} rows, {result['unique_users']} users"
                            )
                except Exception as e:
                    logger.error(f"{model.model_name}: Failed - {e}")
                    failed_models.append({
                        'status': 'error',
                        'model_name': model.model_name,
                        'error': str(e),
                        'error_type': type(e).__name__
                    })

        if not results and not failed_models:
            logger.warning("No data processed")
            return

        # Combine successful results
        combined_df = None
        if results:
            combined_df = pl.concat([r['dataframe'] for r in results])

        timestamp = datetime.now(UTC).strftime('%Y%m%d%H%M') + "all"

        # Save CSV if we have successful results
        csv_path = None
        if combined_df is not None:
            csv_path = Path(OUTPUT_FOLDER) / f"{timestamp}_summary.csv"
            combined_df.write_csv(csv_path)

        # Generate dashboard (including failed models)
        dashboard_gen = AuditDashboardGenerator(combined_df)
        dashboard_path = dashboard_gen.generate(combined_df, timestamp, failed_models)

        total_time = (datetime.now(UTC) - start_time).total_seconds()
        total_rows = sum(r['total_rows'] for r in results) if results else 0

        print(f"\nCompleted in {total_time:.2f}s!")
        if results:
            print(f"Processed {total_rows:,} total rows from {len(results)} model(s)")
        if failed_models:
            print(f"Failed: {len(failed_models)} model(s)")
        if csv_path:
            print(f"CSV: {csv_path}")
        print(f"Dashboard: {dashboard_path}")

    except Exception as e:
        logger.error(f"Error in main: {str(e)}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
