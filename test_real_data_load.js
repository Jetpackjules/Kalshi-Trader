// Test script to debug the real data loading
const fs = require('fs');

// Test date conversion function
function convertDateFormat(selectedDate) {
    try {
        const dateObj = new Date(selectedDate);
        if (isNaN(dateObj.getTime())) {
            throw new Error(`Invalid date: ${selectedDate}`);
        }
        
        const month = dateObj.toLocaleDateString('en-US', { month: 'short' }).toUpperCase();
        const day = String(dateObj.getDate()).padStart(2, '0');
        const year = String(dateObj.getFullYear()).slice(-2);
        const marketDate = `${year}${month}${day}`;
        
        console.log(`Converting ${selectedDate} -> ${marketDate}`);
        return marketDate;
    } catch (error) {
        console.error('Date conversion error:', error);
        return null;
    }
}

// Test CSV parsing
function testCsvParsing() {
    try {
        const csvText = fs.readFileSync('data/candles/KXHIGHNY_candles_5m.csv', 'utf8');
        const lines = csvText.split('\n').filter(line => line.trim());
        
        console.log(`Total lines: ${lines.length}`);
        console.log(`Header: ${lines[0]}`);
        console.log(`Sample data line: ${lines[1]}`);
        
        // Test with August 12, 2025
        const testDate = '2025-08-12';
        const marketDate = convertDateFormat(testDate);
        
        if (marketDate) {
            const matchingLines = lines.filter(line => line.includes(marketDate));
            console.log(`\nFound ${matchingLines.length} lines matching ${marketDate}`);
            
            if (matchingLines.length > 0) {
                console.log('Sample matching lines:');
                matchingLines.slice(0, 3).forEach(line => console.log(line));
            }
        }
        
    } catch (error) {
        console.error('CSV parsing error:', error);
    }
}

// Run tests
console.log('=== Testing Real Data Loading ===');
testCsvParsing();