#### python

import re
import argparse
import datetime
import pandas as pd
import numpy as np
from pathlib import Path
import zoneinfo
import utils
import harp

class RewardAnalyser:
    """
    Class-based analyzer that detects the session stage and runs 
    either the reward-analyser-stage1 or reward-analyser-stage2to8 logic.
    """

    def __init__(self, session_settings):
        self.session_settings = session_settings

    def _reward_analyser_stage1(self, data_path, reward_a=8.0, reward_b=8.0):
        """
        Stage1: Analyzes rewards and session length (reward-analyser-stage1).
        """
        root = Path(data_path)
        behavior_reader = harp.reader.create_reader('device_schemas/behavior.yml', epoch=harp.io.REFERENCE_EPOCH)
        olfactometer_reader = harp.reader.create_reader('device_schemas/olfactometer.yml', epoch=harp.io.REFERENCE_EPOCH)

        # Load data streams
        digital_input_data = utils.load(behavior_reader.DigitalInputState, root/"Behavior")
        pulse_supply_1 = utils.load(behavior_reader.PulseSupplyPort1, root/"Behavior")
        pulse_supply_2 = utils.load(behavior_reader.PulseSupplyPort2, root/"Behavior")
        heartbeat = utils.load(behavior_reader.TimestampSeconds, root/"Behavior")

        # Convert time index to column
        for df in [heartbeat, digital_input_data, pulse_supply_1, pulse_supply_2]:
            df.reset_index(inplace=True)

        # Derive real-time offset
        real_time_str = root.as_posix().split('/')[-1]
        real_time_ref_utc = datetime.datetime.strptime(
            real_time_str, '%Y-%m-%dT%H-%M-%S'
        ).replace(tzinfo=datetime.timezone.utc)
        uk_tz = zoneinfo.ZoneInfo("Europe/London")
        real_time_ref = real_time_ref_utc.astimezone(uk_tz)

        start_time_hardware = heartbeat['Time'].iloc[0]
        start_time_dt = start_time_hardware.to_pydatetime()
        if start_time_dt.tzinfo is None:
            start_time_dt = start_time_dt.replace(tzinfo=uk_tz)
        real_time_offset = real_time_ref - start_time_dt

        # Shift data
        digital_input_data_abs = digital_input_data.copy()
        pulse_supply_1_abs = pulse_supply_1.copy()
        pulse_supply_2_abs = pulse_supply_2.copy()
        for df_abs in [digital_input_data_abs, pulse_supply_1_abs, pulse_supply_2_abs]:
            df_abs['Time'] = df_abs['Time'] + real_time_offset

        # Count reward events
        r1_reward = pulse_supply_1_abs[['Time']].copy()
        r2_reward = pulse_supply_2_abs[['Time']].copy()
        num_r1_rewards = r1_reward.shape[0]
        num_r2_rewards = r2_reward.shape[0]
        total_vol_r1 = num_r1_rewards * reward_a
        total_vol_r2 = num_r2_rewards * reward_b
        total_delivered = total_vol_r1 + total_vol_r2

        # Session length
        start_time_sec = heartbeat['TimestampSeconds'].iloc[0]
        end_time_sec = heartbeat['TimestampSeconds'].iloc[-1]
        session_duration_sec = end_time_sec - start_time_sec
        h = int(session_duration_sec // 3600)
        m = int((session_duration_sec % 3600) // 60)
        s = int(session_duration_sec % 60)

        print(f"Rewards R1: {num_r1_rewards} (Total Volume: {total_vol_r1} µL)")
        print(f"Rewards R2: {num_r2_rewards} (Total Volume: {total_vol_r2} µL)")
        print(f"Overall Volume: {total_delivered} µL")
        print(f"Session Duration: {h}h {m}m {s}s")

    def _reward_analyser_stage2to8(self, data_path, reward_a=8.0, reward_b=8.0):
        """
        Stage2-8: Full session data analysis (reward-analyser-stage2to8).
        With improved error handling for missing or empty data.
        """
        root = Path(data_path)
        behavior_reader = harp.reader.create_reader('device_schemas/behavior.yml', epoch=harp.io.REFERENCE_EPOCH)
        olfactometer_reader = harp.reader.create_reader('device_schemas/olfactometer.yml', epoch=harp.io.REFERENCE_EPOCH)
    
        # Data loading with safe fallbacks for missing data
        try:
            digital_input_data = utils.load(behavior_reader.DigitalInputState, root/"Behavior")
        except ValueError:  # No objects to concatenate - no data
            digital_input_data = pd.DataFrame(columns=['Time', 'DIPort1', 'DIPort2'])
            print("No digital input data found.")
        except Exception as e:
            print(f"Error loading digital input data: {e}")
            digital_input_data = pd.DataFrame(columns=['Time', 'DIPort1', 'DIPort2'])
    
        try:
            pulse_supply_1 = utils.load(behavior_reader.PulseSupplyPort1, root/"Behavior")
        except ValueError:  # No objects to concatenate - no rewards delivered
            pulse_supply_1 = pd.DataFrame(columns=['Time'])
            print("No Reward A (PulseSupplyPort1) data found - possibly no rewards delivered.")
        except Exception as e:
            print(f"Error loading Reward A data: {e}")
            pulse_supply_1 = pd.DataFrame(columns=['Time'])
    
        try:
            pulse_supply_2 = utils.load(behavior_reader.PulseSupplyPort2, root/"Behavior")
        except ValueError:  # No objects to concatenate - no rewards delivered
            pulse_supply_2 = pd.DataFrame(columns=['Time'])
            print("No Reward B (PulseSupplyPort2) data found - possibly no rewards delivered.")
        except Exception as e:
            print(f"Error loading Reward B data: {e}")
            pulse_supply_2 = pd.DataFrame(columns=['Time'])
    
        try:
            olfactometer_valves_0 = utils.load(olfactometer_reader.OdorValveState, root/"Olfactometer0")
        except ValueError:
            olfactometer_valves_0 = pd.DataFrame(columns=['Time', 'Valve0', 'Valve1'])
            print("No olfactometer valve state data found.")
        except Exception as e:
            print(f"Error loading olfactometer valve state data: {e}")
            olfactometer_valves_0 = pd.DataFrame(columns=['Time', 'Valve0', 'Valve1'])
    
        try:
            olfactometer_valves_1 = utils.load(olfactometer_reader.OdorValveState, root/"Olfactometer1")
        except ValueError:
            olfactometer_valves_1 = pd.DataFrame(columns=['Time'])
            print("No data for Olfactometer1 found.")
        except Exception as e:
            print(f"Error loading Olfactometer1 data: {e}")
            olfactometer_valves_1 = pd.DataFrame(columns=['Time'])
    
        try:
            heartbeat = utils.load(behavior_reader.TimestampSeconds, root/"Behavior")
        except Exception as e:
            print(f"Error loading timestamp data: {e}")
            heartbeat = pd.DataFrame(columns=['Time', 'TimestampSeconds'])
    
        # Reset indices for non-empty dataframes
        for df in [digital_input_data, pulse_supply_1, pulse_supply_2, 
                   olfactometer_valves_0, olfactometer_valves_1, heartbeat]:
            if not df.empty:
                df.reset_index(inplace=True)
    
        # Calculate real-time offset only if we have heartbeat data
        real_time_offset = pd.Timedelta(0)
        if not heartbeat.empty and 'Time' in heartbeat.columns and len(heartbeat) > 0:
            try:
                real_time_str = root.as_posix().split('/')[-1]
                real_time_ref_utc = datetime.datetime.strptime(real_time_str, '%Y-%m-%dT%H-%M-%S').replace(tzinfo=datetime.timezone.utc)
                uk_tz = zoneinfo.ZoneInfo("Europe/London")
                real_time_ref = real_time_ref_utc.astimezone(uk_tz)
                
                start_time_hardware = heartbeat['Time'].iloc[0]
                start_time_dt = start_time_hardware.to_pydatetime()
                if start_time_dt.tzinfo is None:
                    start_time_dt = start_time_dt.replace(tzinfo=uk_tz)
                real_time_offset = real_time_ref - start_time_dt
            except Exception as e:
                print(f"Error calculating real-time offset: {e}")
    
        # Create absolute time versions with checks for empty DataFrames
        digital_input_data_abs = digital_input_data.copy() if not digital_input_data.empty else pd.DataFrame()
        pulse_supply_1_abs = pulse_supply_1.copy() if not pulse_supply_1.empty else pd.DataFrame()
        pulse_supply_2_abs = pulse_supply_2.copy() if not pulse_supply_2.empty else pd.DataFrame()
        olfactometer_valves_0_abs = olfactometer_valves_0.copy() if not olfactometer_valves_0.empty else pd.DataFrame()
        olfactometer_valves_1_abs = olfactometer_valves_1.copy() if not olfactometer_valves_1.empty else pd.DataFrame()
    
        # Apply time offset to non-empty DataFrames
        for df_abs in [digital_input_data_abs, pulse_supply_1_abs, pulse_supply_2_abs,
                       olfactometer_valves_0_abs, olfactometer_valves_1_abs]:
            if not df_abs.empty and 'Time' in df_abs.columns:
                df_abs['Time'] = df_abs['Time'] + real_time_offset
    
        # Map heartbeat times if we have data
        timestamp_to_time = pd.Series()
        if not heartbeat.empty and 'Time' in heartbeat.columns and 'TimestampSeconds' in heartbeat.columns:
            heartbeat['Time'] = pd.to_datetime(heartbeat['Time'], errors='coerce')
            timestamp_to_time = pd.Series(data=heartbeat['Time'].values, index=heartbeat['TimestampSeconds'])
    
        def interpolate_time(seconds):
            """Interpolate timestamps from seconds, with safety checks"""
            if timestamp_to_time.empty:
                return pd.NaT
            int_seconds = int(seconds)
            fractional_seconds = seconds % 1
            if int_seconds in timestamp_to_time.index:
                base_time = timestamp_to_time.loc[int_seconds]
                return base_time + pd.to_timedelta(fractional_seconds, unit='s')
            return pd.NaT
    
        # Experiment events - with safety checks
        end_initiation_frames = []
        experiment_events_dir = root / "ExperimentEvents"
        
        if experiment_events_dir.exists():
            csv_files = list(experiment_events_dir.glob("*.csv"))
            print(f"Found {len(csv_files)} experiment event files")
            
            for csv_file in csv_files:
                try:
                    ev_df = pd.read_csv(csv_file)
                    print(f"Processing event file: {csv_file.name} with {len(ev_df)} rows")
                    
                    # Use Seconds field if available, otherwise use Time field
                    if "Seconds" in ev_df.columns and not timestamp_to_time.empty:
                        ev_df = ev_df.sort_values("Seconds").reset_index(drop=True)
                        ev_df["Time"] = ev_df["Seconds"].apply(interpolate_time)
                        print(f"Using Seconds column for interpolation")
                    else:
                        ev_df["Time"] = pd.to_datetime(ev_df["Time"], errors="coerce")
                        print(f"Using Time column directly")
                    
                    if "Time" in ev_df.columns:
                        ev_df["Time"] = ev_df["Time"] + real_time_offset
                        
                        if "Value" in ev_df.columns:
                            print(f"Found Value column with values: {ev_df['Value'].unique()}")
                            eii_df = ev_df[ev_df["Value"] == "EndInitiation"].copy()
                            if not eii_df.empty:
                                print(f"Found {len(eii_df)} EndInitiation events")
                                eii_df["EndInitiation"] = True
                                end_initiation_frames.append(eii_df[["Time", "EndInitiation"]])
                            else:
                                print("No EndInitiation events found in this file")
                        else:
                            print(f"No 'Value' column found in {csv_file.name}")
                except Exception as e:
                    print(f"Error processing event file {csv_file.name}: {e}")
        else:
            print("No ExperimentEvents directory found")
    
        # Safely combine EndInitiation frames
        if len(end_initiation_frames) > 0:
            combined_end_initiation_df = pd.concat(end_initiation_frames, ignore_index=True)
            print(f"Combined {len(combined_end_initiation_df)} EndInitiation events")
        else:
            combined_end_initiation_df = pd.DataFrame(columns=["Time", "EndInitiation"])
            print("No EndInitiation events found - cannot identify trial endings")
    
        # Reward counting - safe for empty DataFrames
        num_r1_rewards = pulse_supply_1_abs.shape[0] if not pulse_supply_1_abs.empty else 0
        num_r2_rewards = pulse_supply_2_abs.shape[0] if not pulse_supply_2_abs.empty else 0
        total_vol_r1 = num_r1_rewards * reward_a
        total_vol_r2 = num_r2_rewards * reward_b
        total_delivered = total_vol_r1 + total_vol_r2
    
        # Session length calculation - safe for empty DataFrame
        if not heartbeat.empty and 'TimestampSeconds' in heartbeat.columns and len(heartbeat) > 1:
            start_time_sec = heartbeat['TimestampSeconds'].iloc[0]
            end_time_sec = heartbeat['TimestampSeconds'].iloc[-1]
            session_duration_sec = end_time_sec - start_time_sec
            h = int(session_duration_sec // 3600)
            m = int((session_duration_sec % 3600) // 60)
            s = int(session_duration_sec % 60)
        else:
            h, m, s = 0, 0, 0
    
        # Always print the reward and session information
        print(f"Number of Reward A (r1) delivered: {num_r1_rewards} (Total Volume: {total_vol_r1} µL)")
        print(f"Number of Reward B (r2) delivered: {num_r2_rewards} (Total Volume: {total_vol_r2} µL)")
        print(f"Overall total volume delivered: {total_delivered} µL\n")
        print(f"Session Duration: {h}h {m}m {s}s\n")
    
        # Only attempt accuracy calculation if we have sufficient data
        try:
            # Safe extraction of data for events
            event_frames = []
            
            # Add r1 poke events if available
            if not digital_input_data_abs.empty and 'DIPort1' in digital_input_data_abs.columns:
                try:
                    r1_poke_df = digital_input_data_abs[digital_input_data_abs['DIPort1'] == True].copy()
                    if not r1_poke_df.empty:
                        r1_poke_df = r1_poke_df[['Time']].copy()
                        r1_poke_df['r1_poke'] = True
                        event_frames.append(r1_poke_df)
                except Exception as e:
                    print(f"Error processing r1 poke events: {e}")
            
            # Add r2 poke events if available
            if not digital_input_data_abs.empty and 'DIPort2' in digital_input_data_abs.columns:
                try:
                    r2_poke_df = digital_input_data_abs[digital_input_data_abs['DIPort2'] == True].copy()
                    if not r2_poke_df.empty:
                        r2_poke_df = r2_poke_df[['Time']].copy()
                        r2_poke_df['r2_poke'] = True
                        event_frames.append(r2_poke_df)
                except Exception as e:
                    print(f"Error processing r2 poke events: {e}")
            
            # Add r1 olfactometer valve events if available
            if not olfactometer_valves_0_abs.empty and 'Valve0' in olfactometer_valves_0_abs.columns:
                try:
                    r1_olf_df = olfactometer_valves_0_abs[olfactometer_valves_0_abs['Valve0'] == True].copy()
                    if not r1_olf_df.empty:
                        r1_olf_df = r1_olf_df[['Time']].copy()
                        r1_olf_df['r1_olf_valve'] = True
                        event_frames.append(r1_olf_df)
                except Exception as e:
                    print(f"Error processing r1 valve events: {e}")
            
            # Add r2 olfactometer valve events if available
            if not olfactometer_valves_0_abs.empty and 'Valve1' in olfactometer_valves_0_abs.columns:
                try:
                    r2_olf_df = olfactometer_valves_0_abs[olfactometer_valves_0_abs['Valve1'] == True].copy()
                    if not r2_olf_df.empty:
                        r2_olf_df = r2_olf_df[['Time']].copy()
                        r2_olf_df['r2_olf_valve'] = True
                        event_frames.append(r2_olf_df)
                except Exception as e:
                    print(f"Error processing r2 valve events: {e}")
            
            # Add EndInitiation events if available
            if not combined_end_initiation_df.empty and 'EndInitiation' in combined_end_initiation_df.columns:
                event_frames.append(combined_end_initiation_df)
                print(f"Added {len(combined_end_initiation_df)} EndInitiation events")
            
            # Only proceed if we have data to analyze
            if event_frames:
                all_events_df = pd.concat(event_frames, ignore_index=True)
                print(f"Combined {len(all_events_df)} total events")
                
                # Explicitly add missing columns with default values to prevent errors
                required_columns = ['timestamp', 'r1_poke', 'r2_poke', 'r1_olf_valve', 'r2_olf_valve', 'EndInitiation']
                for col in required_columns:
                    if col not in all_events_df.columns and col != 'timestamp':
                        all_events_df[col] = False
                
                # Handle the warning about downcasting properly
                all_events_df = all_events_df.fillna(False).infer_objects(copy=False)
                all_events_df.sort_values('Time', inplace=True)
                all_events_df.rename(columns={'Time': 'timestamp'}, inplace=True)
                all_events_df.reset_index(drop=True, inplace=True)
                
                # Check if we have any valid trial data
                has_end_initiation = 'EndInitiation' in all_events_df.columns and any(all_events_df['EndInitiation'])
                has_valve_events = (('r1_olf_valve' in all_events_df.columns and any(all_events_df['r1_olf_valve'])) or
                                    ('r2_olf_valve' in all_events_df.columns and any(all_events_df['r2_olf_valve'])))
                has_poke_events = (('r1_poke' in all_events_df.columns and any(all_events_df['r1_poke'])) or
                                  ('r2_poke' in all_events_df.columns and any(all_events_df['r2_poke'])))
                
                print(f"Data check: EndInitiation events: {has_end_initiation}, " 
                      f"Valve events: {has_valve_events}, Poke events: {has_poke_events}")
                
                if has_end_initiation and has_valve_events and has_poke_events:
                    # Calculate decision accuracy
                    accuracy_summary = calculate_overall_decision_accuracy(all_events_df)
                    
                    # Print accuracy results
                    print("Decision Accuracy (using EndInitiation from experiment events):")
                    print(f"  R1 Trials: {accuracy_summary['r1_total']}, Correct: {accuracy_summary['r1_correct']}, Accuracy: {accuracy_summary['r1_accuracy']:.2f}%")
                    print(f"  R2 Trials: {accuracy_summary['r2_total']}, Correct: {accuracy_summary['r2_correct']}, Accuracy: {accuracy_summary['r2_accuracy']:.2f}%")
                    print(f"  Overall Accuracy: {accuracy_summary['overall_accuracy']:.2f}%")
                else:
                    if not has_end_initiation:
                        print("No EndInitiation events found - cannot identify trial endings")
                    if not has_valve_events:
                        print("No valve activation events found - cannot identify trial types")
                    if not has_poke_events:
                        print("No poke events found - cannot identify animal responses")
                    print("Unable to calculate decision accuracy for this session due to missing event data.")
            else:
                print("No event data available for decision accuracy calculation.")
                
        except Exception as e:
            print(f"Error during decision accuracy calculation: {e}")
            print("Unable to calculate decision accuracy for this session.")

    def _detect_stage(self):
        """
        Extracts the stage from metadata if available.
        Handles nested structure of sequences in metadata.
        """
        stage_found = None
        sequences = self.session_settings.iloc[0]['metadata'].sequences
        
        # Handle the nested list structure
        if isinstance(sequences, list):
            # Iterate through outer list
            for seq_group in sequences:
                if isinstance(seq_group, list):
                    # Iterate through inner list
                    for seq in seq_group:
                        if isinstance(seq, dict) and 'name' in seq:
                            print(f"Found sequence name: {seq['name']}")
                            match = re.search(r'_Stage(\d+)', seq['name'])
                            if match:
                                stage_found = match.group(1)
                                return stage_found
                elif isinstance(seq_group, dict) and 'name' in seq_group:
                    # Handle case where outer list contains dicts directly
                    print(f"Found sequence name: {seq_group['name']}")
                    match = re.search(r'_Stage(\d+)', seq_group['name'])
                    if match:
                        stage_found = match.group(1)
                        return stage_found
        
        print(f"Final stage detected: {stage_found}")
        return stage_found if stage_found else "Unknown"

    def run(self, data_path, reward_a=8.0, reward_b=8.0):
        """
        Run the appropriate reward analysis based on stage detection.
        """
        stage = self._detect_stage()       
        if stage == "1":
            print("Running stage 1 analyzer\n")
            self._reward_analyser_stage1(data_path, reward_a, reward_b)
        else:
            print(f"Running stage {stage} analyzer (stage 2-8)\n")
            self._reward_analyser_stage2to8(data_path, reward_a, reward_b)

    @staticmethod
    def get_decision_accuracy(data_path):
        """
        Static method to calculate decision accuracy for a single session.
        
        Parameters:
        -----------
        data_path : str or Path
            Path to session data directory
            
        Returns:
        --------
        dict
            Dictionary with accuracy metrics or None if calculation fails
        """
        root = Path(data_path)
        
        # Process the given directory directly
        print(f"Processing decision accuracy for: {root}")
        
        # Create readers
        behavior_reader = harp.reader.create_reader('device_schemas/behavior.yml', epoch=harp.io.REFERENCE_EPOCH)
        olfactometer_reader = harp.reader.create_reader('device_schemas/olfactometer.yml', epoch=harp.io.REFERENCE_EPOCH)
        
        try:
            # Data loading with safe fallbacks for missing data
            try:
                digital_input_data = utils.load(behavior_reader.DigitalInputState, root/"Behavior")
                if digital_input_data is None or digital_input_data.empty:
                    print("No digital input data found.")
                    return {
                        'r1_total': 0, 'r1_correct': 0, 'r1_accuracy': 0,
                        'r2_total': 0, 'r2_correct': 0, 'r2_accuracy': 0,
                        'overall_accuracy': 0
                    }
            except ValueError:  # No objects to concatenate - no data
                digital_input_data = pd.DataFrame(columns=['Time', 'DIPort1', 'DIPort2'])
                print("No digital input data found.")
            except Exception as e:
                print(f"Error loading digital input data: {e}")
                return {
                    'r1_total': 0, 'r1_correct': 0, 'r1_accuracy': 0,
                    'r2_total': 0, 'r2_correct': 0, 'r2_accuracy': 0,
                    'overall_accuracy': 0
                }
            
            # Olfactometer data for valve states
            try:
                olfactometer_valves_0 = utils.load(olfactometer_reader.OdorValveState, root/"Olfactometer0")
                if olfactometer_valves_0 is None or olfactometer_valves_0.empty:
                    print("No olfactometer valve state data found.")
                    return {
                        'r1_total': 0, 'r1_correct': 0, 'r1_accuracy': 0,
                        'r2_total': 0, 'r2_correct': 0, 'r2_accuracy': 0,
                        'overall_accuracy': 0
                    }
            except ValueError:
                olfactometer_valves_0 = pd.DataFrame(columns=['Time', 'Valve0', 'Valve1'])
                print("No olfactometer valve state data found.")
            except Exception as e:
                print(f"Error loading olfactometer data: {e}")
                return {
                    'r1_total': 0, 'r1_correct': 0, 'r1_accuracy': 0,
                    'r2_total': 0, 'r2_correct': 0, 'r2_accuracy': 0,
                    'overall_accuracy': 0
                }
            
            # Heartbeat for timestamps
            try:
                heartbeat = utils.load(behavior_reader.TimestampSeconds, root/"Behavior")
                if heartbeat is None or heartbeat.empty:
                    print("No timestamp data found.")
                    return {
                        'r1_total': 0, 'r1_correct': 0, 'r1_accuracy': 0,
                        'r2_total': 0, 'r2_correct': 0, 'r2_accuracy': 0,
                        'overall_accuracy': 0
                    }
            except Exception as e:
                print(f"Error loading timestamp data: {e}")
                return {
                    'r1_total': 0, 'r1_correct': 0, 'r1_accuracy': 0,
                    'r2_total': 0, 'r2_correct': 0, 'r2_accuracy': 0,
                    'overall_accuracy': 0
                }
            
            # Reset indices for non-empty dataframes
            for df in [digital_input_data, olfactometer_valves_0, heartbeat]:
                if not df.empty:
                    df.reset_index(inplace=True)
            
            # Calculate real-time offset only if we have heartbeat data
            real_time_offset = pd.Timedelta(0)
            if not heartbeat.empty and 'Time' in heartbeat.columns and len(heartbeat) > 0:
                try:
                    real_time_str = root.name
                    match = re.search(r'\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}', real_time_str)
                    if match:
                        real_time_str = match.group(0)
                    else:
                        # Try parent directory
                        real_time_str = root.parent.name
                        match = re.search(r'\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}', real_time_str)
                        if match:
                            real_time_str = match.group(0)
                    
                    if re.match(r'\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}', real_time_str):
                        real_time_ref_utc = datetime.datetime.strptime(real_time_str, '%Y-%m-%dT%H-%M-%S')
                        real_time_ref_utc = real_time_ref_utc.replace(tzinfo=datetime.timezone.utc)
                        uk_tz = zoneinfo.ZoneInfo("Europe/London")
                        real_time_ref = real_time_ref_utc.astimezone(uk_tz)
                        
                        start_time_hardware = heartbeat['Time'].iloc[0]
                        start_time_dt = start_time_hardware.to_pydatetime()
                        if start_time_dt.tzinfo is None:
                            start_time_dt = start_time_dt.replace(tzinfo=uk_tz)
                        real_time_offset = real_time_ref - start_time_dt
                except Exception as e:
                    print(f"Error calculating real-time offset: {e}")
            
            # Create absolute time versions with checks for empty DataFrames
            digital_input_data_abs = digital_input_data.copy() if not digital_input_data.empty else pd.DataFrame()
            olfactometer_valves_0_abs = olfactometer_valves_0.copy() if not olfactometer_valves_0.empty else pd.DataFrame()
            
            # Apply time offset to non-empty DataFrames
            for df_abs in [digital_input_data_abs, olfactometer_valves_0_abs]:
                if not df_abs.empty and 'Time' in df_abs.columns:
                    df_abs['Time'] = df_abs['Time'] + real_time_offset
            
            # Map heartbeat times if we have data
            timestamp_to_time = pd.Series()
            if not heartbeat.empty and 'Time' in heartbeat.columns and 'TimestampSeconds' in heartbeat.columns:
                heartbeat['Time'] = pd.to_datetime(heartbeat['Time'], errors='coerce')
                timestamp_to_time = pd.Series(data=heartbeat['Time'].values, index=heartbeat['TimestampSeconds'])
            
            def interpolate_time(seconds):
                """Interpolate timestamps from seconds, with safety checks"""
                if timestamp_to_time.empty:
                    return pd.NaT
                int_seconds = int(seconds)
                fractional_seconds = seconds % 1
                if int_seconds in timestamp_to_time.index:
                    base_time = timestamp_to_time.loc[int_seconds]
                    return base_time + pd.to_timedelta(fractional_seconds, unit='s')
                return pd.NaT
            
            # Experiment events - with safety checks
            end_initiation_frames = []
            experiment_events_dir = root / "ExperimentEvents"
            
            if experiment_events_dir.exists():
                csv_files = list(experiment_events_dir.glob("*.csv"))
                print(f"Found {len(csv_files)} experiment event files")
                
                for csv_file in csv_files:
                    try:
                        ev_df = pd.read_csv(csv_file)
                        print(f"Processing event file: {csv_file.name} with {len(ev_df)} rows")
                        
                        # Use Seconds field if available, otherwise use Time field
                        if "Seconds" in ev_df.columns and not timestamp_to_time.empty:
                            ev_df = ev_df.sort_values("Seconds").reset_index(drop=True)
                            ev_df["Time"] = ev_df["Seconds"].apply(interpolate_time)
                            print(f"Using Seconds column for interpolation")
                        else:
                            ev_df["Time"] = pd.to_datetime(ev_df["Time"], errors="coerce")
                            print(f"Using Time column directly")
                        
                        if "Time" in ev_df.columns:
                            ev_df["Time"] = ev_df["Time"] + real_time_offset
                            
                            if "Value" in ev_df.columns:
                                print(f"Found Value column with values: {ev_df['Value'].unique()}")
                                eii_df = ev_df[ev_df["Value"] == "EndInitiation"].copy()
                                if not eii_df.empty:
                                    print(f"Found {len(eii_df)} EndInitiation events")
                                    eii_df["EndInitiation"] = True
                                    end_initiation_frames.append(eii_df[["Time", "EndInitiation"]])
                    except Exception as e:
                        print(f"Error processing event file {csv_file.name}: {e}")
            else:
                print("No ExperimentEvents directory found")
            
            # Safely combine EndInitiation frames
            if len(end_initiation_frames) > 0:
                combined_end_initiation_df = pd.concat(end_initiation_frames, ignore_index=True)
                print(f"Combined {len(combined_end_initiation_df)} EndInitiation events")
            else:
                combined_end_initiation_df = pd.DataFrame(columns=["Time", "EndInitiation"])
                print("No EndInitiation events found - cannot identify trial endings")
            
            # Prepare event frames for analysis
            event_frames = []
            
            # Add r1 poke events if available
            if not digital_input_data_abs.empty and 'DIPort1' in digital_input_data_abs.columns:
                try:
                    r1_poke_df = digital_input_data_abs[digital_input_data_abs['DIPort1'] == True].copy()
                    if not r1_poke_df.empty:
                        r1_poke_df = r1_poke_df[['Time']].copy()
                        r1_poke_df['r1_poke'] = True
                        event_frames.append(r1_poke_df)
                        print(f"Added {len(r1_poke_df)} r1 poke events")
                except Exception as e:
                    print(f"Error processing r1 poke events: {e}")
            
            # Add r2 poke events if available
            if not digital_input_data_abs.empty and 'DIPort2' in digital_input_data_abs.columns:
                try:
                    r2_poke_df = digital_input_data_abs[digital_input_data_abs['DIPort2'] == True].copy()
                    if not r2_poke_df.empty:
                        r2_poke_df = r2_poke_df[['Time']].copy()
                        r2_poke_df['r2_poke'] = True
                        event_frames.append(r2_poke_df)
                        print(f"Added {len(r2_poke_df)} r2 poke events")
                except Exception as e:
                    print(f"Error processing r2 poke events: {e}")
            
            # Add r1 olfactometer valve events if available
            if not olfactometer_valves_0_abs.empty and 'Valve0' in olfactometer_valves_0_abs.columns:
                try:
                    r1_olf_df = olfactometer_valves_0_abs[olfactometer_valves_0_abs['Valve0'] == True].copy()
                    if not r1_olf_df.empty:
                        r1_olf_df = r1_olf_df[['Time']].copy()
                        r1_olf_df['r1_olf_valve'] = True
                        event_frames.append(r1_olf_df)
                        print(f"Added {len(r1_olf_df)} r1 valve events")
                except Exception as e:
                    print(f"Error processing r1 valve events: {e}")
            
            # Add r2 olfactometer valve events if available
            if not olfactometer_valves_0_abs.empty and 'Valve1' in olfactometer_valves_0_abs.columns:
                try:
                    r2_olf_df = olfactometer_valves_0_abs[olfactometer_valves_0_abs['Valve1'] == True].copy()
                    if not r2_olf_df.empty:
                        r2_olf_df = r2_olf_df[['Time']].copy()
                        r2_olf_df['r2_olf_valve'] = True
                        event_frames.append(r2_olf_df)
                        print(f"Added {len(r2_olf_df)} r2 valve events")
                except Exception as e:
                    print(f"Error processing r2 valve events: {e}")
            
            # Add EndInitiation events if available
            if not combined_end_initiation_df.empty and 'EndInitiation' in combined_end_initiation_df.columns:
                event_frames.append(combined_end_initiation_df)
            
            # Only proceed if we have data to analyze
            if event_frames:
                try:
                    all_events_df = pd.concat(event_frames, ignore_index=True)
                    print(f"Combined {len(all_events_df)} total events")
                    
                    # Explicitly add missing columns with default values to prevent errors
                    required_columns = ['timestamp', 'r1_poke', 'r2_poke', 'r1_olf_valve', 'r2_olf_valve', 'EndInitiation']
                    for col in required_columns:
                        if col not in all_events_df.columns and col != 'timestamp':
                            all_events_df[col] = False
                    
                    # Handle the warning about downcasting properly
                    all_events_df = all_events_df.fillna(False).infer_objects(copy=False)
                    all_events_df.sort_values('Time', inplace=True)
                    all_events_df.rename(columns={'Time': 'timestamp'}, inplace=True)
                    all_events_df.reset_index(drop=True, inplace=True)
                    
                    # Check if we have any valid trial data
                    has_end_initiation = 'EndInitiation' in all_events_df.columns and any(all_events_df['EndInitiation'])
                    has_valve_events = (('r1_olf_valve' in all_events_df.columns and any(all_events_df['r1_olf_valve'])) or
                                        ('r2_olf_valve' in all_events_df.columns and any(all_events_df['r2_olf_valve'])))
                    has_poke_events = (('r1_poke' in all_events_df.columns and any(all_events_df['r1_poke'])) or
                                      ('r2_poke' in all_events_df.columns and any(all_events_df['r2_poke'])))
                    
                    print(f"Data check: EndInitiation events: {has_end_initiation}, " 
                          f"Valve events: {has_valve_events}, Poke events: {has_poke_events}")
                    
                    if has_end_initiation and has_valve_events and has_poke_events:
                        # Calculate decision accuracy
                        accuracy_data = calculate_overall_decision_accuracy(all_events_df)
                        return accuracy_data
                    else:
                        if not has_end_initiation:
                            print("No EndInitiation events found - cannot identify trial endings")
                        if not has_valve_events:
                            print("No valve activation events found - cannot identify trial types")
                        if not has_poke_events:
                            print("No poke events found - cannot identify animal responses")
                        
                        # Return zeros instead of None for better downstream handling
                        return {
                            'r1_total': 0, 'r1_correct': 0, 'r1_accuracy': 0,
                            'r2_total': 0, 'r2_correct': 0, 'r2_accuracy': 0,
                            'overall_accuracy': 0
                        }
                
                except Exception as e:
                    print(f"Error processing event data: {e}")
                    # Return zeros instead of None
                    return {
                        'r1_total': 0, 'r1_correct': 0, 'r1_accuracy': 0,
                        'r2_total': 0, 'r2_correct': 0, 'r2_accuracy': 0,
                        'overall_accuracy': 0
                    }
            else:
                print("No events available for decision accuracy calculation")
                # Return zeros instead of None
                return {
                    'r1_total': 0, 'r1_correct': 0, 'r1_accuracy': 0,
                    'r2_total': 0, 'r2_correct': 0, 'r2_accuracy': 0,
                    'overall_accuracy': 0
                }
        
        except Exception as e:
            print(f"Error during decision accuracy calculation: {e}")
            # Return zeros instead of None
            return {
                'r1_total': 0, 'r1_correct': 0, 'r1_accuracy': 0,
                'r2_total': 0, 'r2_correct': 0, 'r2_accuracy': 0,
                'overall_accuracy': 0
            }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Combine Stage1 & Stage2-8 Reward Analysis.")
    parser.add_argument("data_path", help="Path to the root folder containing behavior data.")
    parser.add_argument("--reward_a", type=float, default=8.0, help="Volume (µL) per Reward A.")
    parser.add_argument("--reward_b", type=float, default=8.0, help="Volume (µL) per Reward B.")
    args = parser.parse_args()

    print("Please instantiate RewardAnalyser with your session_settings and call .run(data_path, reward_a, reward_b).")

def interpolate_time(seconds):
    """Interpolate timestamps from seconds, with safety checks"""
    if timestamp_to_time.empty:
        return pd.NaT
    int_seconds = int(seconds)
    fractional_seconds = seconds % 1
    if int_seconds in timestamp_to_time.index:
        base_time = timestamp_to_time.loc[int_seconds]
        return base_time + pd.to_timedelta(fractional_seconds, unit='s')
    return pd.NaT

# Add module-level function to expose the static method
def get_decision_accuracy(data_path):
    """
    Calculate decision accuracy for a single session.
    
    Parameters:
    -----------
    data_path : str or Path
        Path to session data directory
        
    Returns:
    --------
    dict
        Dictionary with accuracy metrics or None if calculation fails
    """
    return RewardAnalyser.get_decision_accuracy(data_path)

def detect_stage(root):
    """
    Extracts the stage from metadata if available.
    Handles nested structure of sequences in metadata.
    """
    
    path_root = Path(root)
    metadata_reader = utils.SessionData()
    session_settings = utils.load_json(metadata_reader, path_root/"SessionSettings")
    stage_found = None
    sequences = session_settings.iloc[0]['metadata'].sequences
        
    # Handle the nested list structure
    if isinstance(sequences, list):
        # Iterate through outer list
        for seq_group in sequences:
            if isinstance(seq_group, list):
                # Iterate through inner list
                for seq in seq_group:
                    if isinstance(seq, dict) and 'name' in seq:
                        print(f"Found sequence name: {seq['name']}")
                        match = re.search(r'_Stage(\d+)', seq['name'])
                        if match:
                            stage_found = match.group(1)
                            return stage_found
            elif isinstance(seq_group, dict) and 'name' in seq_group:
                # Handle case where outer list contains dicts directly
                print(f"Found sequence name: {seq_group['name']}")
                match = re.search(r'_Stage(\d+)', seq_group['name'])
                if match:
                    stage_found = match.group(1)
                    return stage_found
        
    print(f"Final stage detected: {stage_found}")
    return stage_found if stage_found else "Unknown"

def calculate_overall_decision_accuracy(events_df):
    """
    Calculate decision accuracy for r1/r2 trials.
    
    Parameters:
    -----------
    events_df : pandas.DataFrame
        DataFrame containing trial events with columns: 'timestamp', 'EndInitiation',
        'r1_olf_valve', 'r2_olf_valve', 'r1_poke', 'r2_poke'
        
    Returns:
    --------
    dict
        Dictionary containing accuracy metrics for r1, r2, and overall trials
    """
    # Ensure events are in chronological order
    events_df = events_df.sort_values('timestamp').reset_index(drop=True)
    
    # Initialize counters
    r1_correct = 0
    r1_total = 0
    r2_correct = 0
    r2_total = 0
    
    # Find all trial end points
    end_initiation_indices = events_df.index[events_df['EndInitiation'] == True].tolist()

    # Process each trial
    for end_idx in end_initiation_indices:
        # Determine trial type (r1 or r2) by finding the most recent valve activation
        closest_valve_idx = None
        trial_type = None
        for i in range(end_idx - 1, -1, -1):
            if events_df.loc[i, 'r1_olf_valve']:
                closest_valve_idx = i
                trial_type = 'r1'
                break
            elif events_df.loc[i, 'r2_olf_valve']:
                closest_valve_idx = i
                trial_type = 'r2'
                break
                
        # Skip if no valve activation found before this trial end
        if closest_valve_idx is None:
            continue
            
        # Count trial by type
        if trial_type == 'r1':
            r1_total += 1
        else:
            r2_total += 1
            
        # Find the first poke after trial end
        for j in range(end_idx + 1, len(events_df)):
            if events_df.loc[j, 'r1_poke'] or events_df.loc[j, 'r2_poke']:
                # Correct if poke matches trial type
                if trial_type == 'r1' and events_df.loc[j, 'r1_poke']:
                    r1_correct += 1
                elif trial_type == 'r2' and events_df.loc[j, 'r2_poke']:
                    r2_correct += 1
                break

    # Calculate accuracy percentages with safety checks for division by zero
    r1_accuracy = (r1_correct / r1_total * 100) if r1_total > 0 else 0
    r2_accuracy = (r2_correct / r2_total * 100) if r2_total > 0 else 0
    overall_accuracy = ((r1_correct + r2_correct) / (r1_total + r2_total) * 100) if (r1_total + r2_total) > 0 else 0
    
    # Return detailed accuracy metrics
    return {
        'r1_total': r1_total,
        'r1_correct': r1_correct,
        'r1_accuracy': r1_accuracy,
        'r2_total': r2_total,
        'r2_correct': r2_correct,
        'r2_accuracy': r2_accuracy,
        'overall_accuracy': overall_accuracy
    }

