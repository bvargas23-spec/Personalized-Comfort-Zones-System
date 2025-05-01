// api_gateway.js
// API Gateway Integration for PCZS

// Configuration
const API_ENDPOINT = 'https://kyqa443czf.execute-api.us-east-2.amazonaws.com/prod';

// Function to save user preferences
async function savePreferences(preferences) {
    try {
        console.log('Saving preferences:', preferences);
        const response = await fetch(`${API_ENDPOINT}/preferences`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(preferences),
        });
        
        if (!response.ok) {
            throw new Error(`API error: ${response.status}`);
        }
        
        const data = await response.json();
        console.log('Preferences saved:', data);
        alert('Your comfort preferences have been saved!');
        return data;
    } catch (error) {
        console.error('Error saving preferences:', error);
        alert('Error saving preferences: ' + error.message);
    }
}

// Function to get user preferences
async function getPreferences(userId, workspaceId) {
    try {
        const response = await fetch(`${API_ENDPOINT}/preferences?user_id=${userId}&workspace_id=${workspaceId}`);
        
        if (!response.ok) {
            throw new Error(`API error: ${response.status}`);
        }
        
        const data = await response.json();
        console.log('Retrieved preferences:', data);
        
        // Update form with retrieved preferences
        if (data) {
            document.getElementById('preferred-temp').value = data.preferred_temp;
            document.getElementById('temp-val').textContent = data.preferred_temp;
            
            document.getElementById('temp-threshold').value = data.temp_threshold;
            document.getElementById('temp-thresh-val').textContent = data.temp_threshold;
            
            document.getElementById('preferred-humidity').value = data.preferred_humidity;
            document.getElementById('humidity-val').textContent = data.preferred_humidity;
            
            document.getElementById('humidity-threshold').value = data.humidity_threshold;
            document.getElementById('humidity-thresh-val').textContent = data.humidity_threshold;
        }
        
        return data;
    } catch (error) {
        console.error('Error getting preferences:', error);
        return null;
    }
}

// Function to get current telemetry data
async function getCurrentTelemetry(workspaceId) {
    try {
        const response = await fetch(`${API_ENDPOINT}/telemetry?workspace_id=${workspaceId}`);
        
        if (!response.ok) {
            throw new Error(`API error: ${response.status}`);
        }
        
        const data = await response.json();
        console.log('Retrieved telemetry:', data);
        return data;
    } catch (error) {
        console.error('Error getting telemetry:', error);
        return null;
    }
}

// NEW FUNCTION: Get historical telemetry data
async function getHistoricalTelemetry(workspaceId, hours = 24) {
    try {
        const response = await fetch(`${API_ENDPOINT}/telemetry/history?workspace_id=${workspaceId}&hours=${hours}`);
        
        if (!response.ok) {
            throw new Error(`API error: ${response.status}`);
        }
        
        const data = await response.json();
        console.log('Retrieved historical telemetry:', data);
        return data;
    } catch (error) {
        console.error('Error getting historical telemetry:', error);
        return [];
    }
}

// Function to process historical data for charting
function processHistoricalData(historyData) {
    const processed = {
        timestamps: [],
        temperature: [],
        humidity: [],
        occupied: []
    };
    
    // Sort by timestamp (newest last)
    historyData.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
    
    // Process each data point
    historyData.forEach(item => {
        const date = new Date(item.timestamp);
        const timeString = date.getHours() + ':' + 
                          (date.getMinutes() < 10 ? '0' : '') + date.getMinutes();
        
        processed.timestamps.push(timeString);
        processed.temperature.push(item.temperature);
        processed.humidity.push(item.humidity);
        processed.occupied.push(item.occupied);
    });
    
    return processed;
}

// Initialize dashboard with preferences when page loads
document.addEventListener('DOMContentLoaded', function() {
    // Get user preferences when page loads
    const userId = 'user_1'; // In a real app, this would come from authentication
    const workspaceId = document.getElementById('workspace-id').value;
    getPreferences(userId, workspaceId);
    
    // Load historical data if available
    loadHistoricalData(workspaceId);
});

// Function to load and process historical data
async function loadHistoricalData(workspaceId) {
    const historicalData = await getHistoricalTelemetry(workspaceId);
    if (historicalData && historicalData.length > 0) {
        const processedData = processHistoricalData(historicalData);
        
        // If you have a global chart object defined elsewhere
        if (window.sensorData && window.sensorChart) {
            // Update with historical data
            window.sensorData.timestamps = processedData.timestamps;
            window.sensorData.temperature = processedData.temperature;
            window.sensorData.humidity = processedData.humidity;
            
            // Fill preferred values arrays with current preferences
            const prefTemp = parseFloat(document.getElementById('preferred-temp').value);
            const prefHum = parseFloat(document.getElementById('preferred-humidity').value);
            
            window.sensorData.preferredTemp = Array(processedData.timestamps.length).fill(prefTemp);
            window.sensorData.preferredHumidity = Array(processedData.timestamps.length).fill(prefHum);
            
            // Update chart
            window.sensorChart.update();
        }
    }
}

// Make functions available globally
window.savePreferences = savePreferences;
window.getPreferences = getPreferences;
window.getCurrentTelemetry = getCurrentTelemetry;
window.getHistoricalTelemetry = getHistoricalTelemetry;
window.processHistoricalData = processHistoricalData;
window.loadHistoricalData = loadHistoricalData;