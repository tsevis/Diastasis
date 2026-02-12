# Diastasis - SVG Layer Separation Tool

**Diastasis** is a sophisticated SVG processing tool that automatically separates overlapping shapes in SVG files into distinct layers based on graph coloring algorithms. This tool is particularly useful for preparing SVG files for laser cutting, 3D printing, or other manufacturing processes where overlapping elements need to be separated onto different layers to avoid interference.

## Features

- **Automatic Layer Separation**: Automatically detects overlapping shapes in SVG files and assigns them to different layers
- **Multiple Coloring Algorithms**: Choose from various graph coloring algorithms including DSATUR, Largest First, Independent Set, and more
- **Optimization Options**: Apply post-processing optimization to minimize the number of layers
- **Force K Algorithm**: Force the output to a specific number of layers, minimizing overlap within each layer
- **Visual Preview**: Built-in GUI with SVG preview functionality
- **Crop Marks Generation**: Automatically adds crop marks to facilitate alignment during manufacturing
- **Multi-threaded Processing**: Efficient processing using spatial indexing and parallel computation

## Installation

1. Clone the repository:
```bash
git clone https://github.com/tsevis/diastasis.git
cd diastasis
```

2. Install the required dependencies:
```bash
pip install -r requirements.txt
```

## Usage

### GUI Mode (Recommended)

Launch the graphical interface:
```bash
python gui.py
```

Or run the shell script:
```bash
./run_gui.sh
```

The GUI provides the following functionality:
- Select SVG files for processing
- Choose from multiple graph coloring algorithms
- Configure optimization settings
- Preview the input SVG
- View processing results and statistics
- Save the layered output

### Command Line Mode

You can also use the tool programmatically by importing the main functions:

```python
from main import run_diastasis, save_layers_to_files

# Process an SVG file
shapes, coloring, summary, svg_width, svg_height = run_diastasis(
    "input.svg", 
    algorithm="DSATUR", 
    use_optimizer=True
)

# Save the results
save_layers_to_files(
    shapes, 
    coloring, 
    "output_directory", 
    "output_filename", 
    svg_width, 
    svg_height
)
```

## Algorithms

The tool implements several graph coloring algorithms:

- **Largest First (Welsh-Powell)**: Fast algorithm that colors nodes with the most neighbors first
- **DSATUR**: Good balance of speed and quality, prioritizes nodes with the most distinctly colored neighbors
- **Independent Set**: Potentially very high quality, finds groups of non-overlapping shapes to color at once
- **Smallest Last**: Good quality, colors nodes in reverse order of their removal in a graph simplification process
- **Random Sequential**: Fastest but least optimal, colors nodes in a random order
- **Connected Sequential BFS/DFS**: Colors nodes based on Breadth-First or Depth-First Search traversal
- **Force K**: Forces the output to a specific number of layers, minimizing overlap within each layer

## How It Works

1. **Parsing**: The SVG file is parsed to extract geometric shapes (rectangles, circles, ellipses, polygons, paths)
2. **Overlap Detection**: The system detects overlapping shapes and calculates overlap areas using spatial indexing
3. **Graph Construction**: A graph is built where each node represents a shape and edges represent overlaps
4. **Graph Coloring**: The graph is colored using the selected algorithm, where each color represents a layer
5. **Layer Assignment**: Shapes are assigned to layers based on their color, ensuring no overlapping shapes share the same layer
6. **Output Generation**: A new SVG file is created with shapes organized into separate layers

## Output

The processed SVG file contains:
- Separate layers for non-overlapping shapes
- Color-coded shapes for easy identification
- Crop marks for alignment during manufacturing
- Proper SVG structure compatible with design software like Adobe Illustrator

## Dependencies

- `svgpathtools`: For parsing SVG path data
- `shapely`: For geometric operations and spatial analysis
- `rtree`: For spatial indexing to accelerate overlap detection
- `networkx`: For graph construction and coloring algorithms
- `numpy`: For numerical computations
- `lxml`: For XML parsing of SVG files
- `Pillow` and `cairosvg`: For SVG preview in the GUI
- `matplotlib`: For visualization (optional)

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- The graph coloring algorithms are implemented using NetworkX
- Geometric operations are powered by Shapely
- SVG parsing uses svgpathtools and lxml
