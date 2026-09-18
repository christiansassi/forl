//
//  FORLWidgetBundle.swift
//  Everything this extension offers the system.
//
//  One widget in two sizes, and on macOS 26 a Control Center control as well,
//  all reading the same file the app writes.
//

import WidgetKit
import SwiftUI

/// The bundle macOS loads.
@main
struct FORLWidgetBundle: WidgetBundle {
	@WidgetBundleBuilder
	var body: some Widget {
		UsageWidget()
		if #available(macOS 26.0, *) {
			UsageControl()
		}
	}
}
