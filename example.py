#!/usr/bin/env python3
"""
Example usage of the Landsat GIF Animator
"""

from animate import LandsatAnimator

def main():
    # Create animator instance
    animator = LandsatAnimator()
    
    # Example 1: San Francisco with natural color
    print("Example 1: San Francisco - Natural Color")
    animator.generate_animation(
        location="San Francisco",
        mode="rgb",
        cloud_cover=10,
        fps=12
    )
    
    # Example 2: Amazon rainforest with NDVI
    print("\nExample 2: Amazon - NDVI")
    animator.generate_animation(
        location="-3.4653,-62.2159",
        mode="ndvi",
        cloud_cover=10,
        fps=12
    )

if __name__ == '__main__':
    main()
