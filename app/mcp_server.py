import logging
from mcp.server.fastmcp import FastMCP

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("swimsafe-mcp")

mcp = FastMCP("SwimSafe AI MCP Server")

@mcp.tool()
def get_chemical_guidelines() -> str:
    """
    Get the official chemical guidelines and safety thresholds for swimming pool water.
    
    Returns:
        A text description of standard safety ranges for free chlorine, pH, cyanuric acid, etc.
    """
    logger.info("Serving chemical guidelines")
    return """
    Official Swimming Pool Chemical Guidelines:
    - Free Chlorine:
      * Standard Pools: 1.0 - 3.0 ppm (parts per million)
      * Spas/Hot Tubs: 3.0 - 5.0 ppm
      * Absolute Minimum: 1.0 ppm
      * Shock/Superchlorination: 10.0 ppm+ (do not swim above 10.0 ppm)
    - pH Level:
      * Ideal Range: 7.2 - 7.8
      * Comfort Range: 7.4 - 7.6 (matches human tear duct pH)
      * Too Low (<7.0): Acidic, causes skin/eye irritation and corrodes equipment.
      * Too High (>7.8): Basic, causes cloudy water, scaling, and severely reduces chlorine effectiveness.
    - Cyanuric Acid (Stabilizer):
      * Ideal Range: 30 - 50 ppm (protects chlorine from UV degradation)
      * Maximum Safe: 100 ppm
      * Too High (>100 ppm): Causes chlorine lock (chlorine is present but ineffective).
    - Water Clarity:
      * Must be crystal clear. The main drain/deep end must be clearly visible.
    """

@mcp.tool()
def diagnose_water_issues(clarity: str, ph: float, chlorine: float) -> str:
    """
    Diagnose common pool water issues based on basic metrics and recommend solutions.
    
    Args:
        clarity: Clarity of the pool water ('clear', 'cloudy', 'turbid')
        ph: Measured pH level of the pool
        chlorine: Measured free chlorine level in ppm
        
    Returns:
        A diagnostic summary with corrective action recommendations.
    """
    logger.info(f"Diagnosing issues: clarity={clarity}, ph={ph}, chlorine={chlorine}")
    diagnoses = []
    recommendations = []
    
    # 1. Check chlorine issues
    if chlorine < 1.0:
        diagnoses.append("Critically low sanitizer (free chlorine < 1.0 ppm). Water is unsafe.")
        recommendations.append("Add sanitizing chlorine (liquid chlorine or cal-hypo shock) immediately to boost levels to 3.0 ppm.")
    elif chlorine > 10.0:
        diagnoses.append("Toxic sanitizer level (free chlorine > 10.0 ppm). Highly corrosive.")
        recommendations.append("Do not swim. Wait for UV light to naturally degrade chlorine, or use a chlorine neutralizer (sodium thiosulfate).")

    # 2. Check pH issues
    if ph < 7.0:
        diagnoses.append("Corrosive acidic water (pH < 7.0). Causes skin/eye burns.")
        recommendations.append("Add soda ash (sodium carbonate) or baking soda (sodium bicarbonate) to raise pH and alkalinity.")
    elif ph > 7.8:
        diagnoses.append("Scaling basic water (pH > 7.8). Inactivates chlorine.")
        recommendations.append("Add muriatic acid (hydrochloric acid) or dry acid (sodium bisulfate) to lower pH.")

    # 3. Check clarity issues
    if clarity != "clear":
        if chlorine < 1.0:
            diagnoses.append("Algae bloom or bacterial buildup suspected due to low chlorine and poor clarity.")
            recommendations.append("Perform a 'superchlorination' shock to raise chlorine above 10 ppm, run the filter continuously, and brush pool walls.")
        else:
            diagnoses.append("Cloudy water with sufficient chlorine. Likely filtration failure or high calcium scaling.")
            recommendations.append("Run the pool filter for 24-48 hours. Add pool clarifier if needed, and verify calcium hardness / alkalinity.")

    if not diagnoses:
        return "Water metrics appear balanced. No immediate issues detected. Keep up the regular testing!"
        
    output = "--- Diagnostic Report ---\n"
    output += "Detected Issues:\n" + "\n".join(f"- {d}" for d in diagnoses) + "\n\n"
    output += "Action Recommendations:\n" + "\n".join(f"- {r}" for r in recommendations)
    return output

@mcp.tool()
def calculate_lsi(ph: float, water_temp_f: float, calcium_hardness: float, total_alkalinity: float, cyanuric_acid: float) -> str:
    """
    Calculate the Langelier Saturation Index (LSI) to determine water stability (corrosive, balanced, or scaling).
    
    Args:
        ph: Measured pH
        water_temp_f: Water temperature in Fahrenheit
        calcium_hardness: Calcium hardness in ppm (typical: 200-400 ppm)
        total_alkalinity: Total alkalinity in ppm (typical: 80-120 ppm)
        cyanuric_acid: Cyanuric acid stabilizer in ppm (typical: 30-50 ppm)
        
    Returns:
        LSI value and water stability classification.
    """
    logger.info("Calculating LSI")
    
    # Temperature Factor (TF)
    tf = 0.0
    if water_temp_f < 32: tf = 0.0
    elif water_temp_f < 53: tf = 0.3
    elif water_temp_f < 66: tf = 0.4
    elif water_temp_f < 77: tf = 0.5
    elif water_temp_f < 84: tf = 0.6
    elif water_temp_f < 94: tf = 0.7
    else: tf = 0.8 # Spa temps
    
    # Calcium Hardness Factor (CF)
    import math
    cf = math.log10(max(10.0, calcium_hardness)) - 0.7
    
    # Alkalinity Factor (AF) - corrected for CYA (Cyanuric Acid correction)
    corrected_alkalinity = total_alkalinity - (cyanuric_acid / 3.0)
    af = math.log10(max(10.0, corrected_alkalinity)) - 0.7
    
    # LSI Formula: pH + TF + CF + AF - 12.1
    # 12.1 is constant for TDS < 1000 ppm
    lsi = ph + tf + cf + af - 12.1
    
    if lsi < -0.3:
        status = "Corrosive / Under-saturated (can damage plaster, concrete, and metal parts)"
    elif lsi > 0.3:
        status = "Scaling / Over-saturated (can deposit calcium scale on surfaces and plumbing, cloudy water)"
    else:
        status = "Balanced and Stable water"
        
    return f"LSI Value: {lsi:.2f}\nWater Status: {status}\n(Ideal LSI is between -0.3 and +0.3)"

if __name__ == "__main__":
    mcp.run()
